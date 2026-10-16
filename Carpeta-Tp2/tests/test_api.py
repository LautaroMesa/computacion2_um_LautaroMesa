"""La API: respuestas, validación, códigos de estado."""
import time

from conftest import crear, esperar_estado


async def test_post_responde_sin_esperar_a_la_tarea(armar_api):
    async with armar_api() as (c, _):
        t0 = time.perf_counter()
        r = await c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 5}})
        assert time.perf_counter() - t0 < 0.5
        assert r.status_code == 202
        assert r.headers['location'] == f'/tareas/{r.json()["id"]}'
        assert r.json()['estado'] in ('pendiente', 'ejecutando')


async def test_validacion_rechaza_con_422(armar_api):
    async with armar_api() as (c, _):
        malos = [
            {'tipo': 'volar', 'parametros': {}},
            {'tipo': 'esperar', 'parametros': {}},
            {'tipo': 'esperar', 'parametros': {'segundos': -1}},
            {'tipo': 'esperar', 'parametros': {'segundos': 1}, 'timeout': 0},
            {'tipo': 'hashear', 'parametros': {'texto': 'a', 'iteraciones': 0}},
            {'tipo': 'descargar', 'parametros': {'urls': []}},
            {'tipo': 'descargar', 'parametros': {'urls': ['ftp://x.com/a']}},
        ]
        for cuerpo in malos:
            r = await c.post('/tareas', json=cuerpo)
            assert r.status_code == 422, cuerpo
        # Ninguna llegó al registro
        assert (await c.get('/estadisticas')).json()['total'] == 0


async def test_404_y_409(armar_api):
    async with armar_api() as (c, _):
        assert (await c.get('/tareas/999')).status_code == 404
        assert (await c.delete('/tareas/999')).status_code == 404
        tid = await crear(c, 'esperar', {'segundos': 0})
        await esperar_estado(c, tid)
        assert (await c.delete(f'/tareas/{tid}')).status_code == 409


async def test_esperar_completa_con_resultado_y_tiempos(armar_api):
    async with armar_api() as (c, _):
        tid = await crear(c, 'esperar', {'segundos': 0.3})
        t = await esperar_estado(c, tid)
        assert t['estado'] == 'completada'
        assert t['resultado']['durmio'] >= 0.3
        assert 0.3 <= t['duracion'] < 1
        assert t['iniciada'] and t['terminada'] and t['worker'] is not None


async def test_listar_filtra_por_estado(armar_api):
    async with armar_api(workers=1) as (c, _):
        a = await crear(c, 'esperar', {'segundos': 0})
        await esperar_estado(c, a)
        b = await crear(c, 'esperar', {'segundos': 5})
        await crear(c, 'esperar', {'segundos': 5})
        await esperar_estado(c, b, estados=('ejecutando',))   # que el worker la tome
        pendientes = (await c.get('/tareas', params={'estado': 'pendiente'})).json()
        completadas = (await c.get('/tareas', params={'estado': 'completada'})).json()
        assert [t['id'] for t in completadas] == [a]
        assert len(pendientes) == 1
        assert (await c.get('/tareas', params={'estado': 'otro'})).status_code == 422


async def test_estadisticas(armar_api):
    async with armar_api(workers=3) as (c, _):
        for s in (0, 0, 5):
            await crear(c, 'esperar', {'segundos': s})
        await esperar_estado(c, 1)
        await esperar_estado(c, 2)
        await esperar_estado(c, 3, estados=('ejecutando',))
        e = (await c.get('/estadisticas')).json()
        assert e['total'] == 3
        assert e['por_estado']['completada'] == 2
        assert e['por_estado']['ejecutando'] == 1
        assert e['workers_total'] == 3
        assert e['workers_ocupados'] == 1
        assert e['tiempo_promedio_ejecucion']['esperar'] is not None


async def test_cola_llena_devuelve_503(armar_api):
    async with armar_api(workers=1, max_cola=1) as (c, _):
        await crear(c, 'esperar', {'segundos': 5})                  # la toma el worker
        await esperar_estado(c, 1, estados=('ejecutando',))
        await crear(c, 'esperar', {'segundos': 5})                  # ocupa la cola
        r = await c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 5}})
        assert r.status_code == 503
        assert 'retry-after' in r.headers
        # La rechazada no queda registrada
        assert (await c.get('/estadisticas')).json()['total'] == 2
