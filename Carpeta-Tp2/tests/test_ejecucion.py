"""Ejecución: concurrencia, cancelación, timeouts, robustez y apagado."""
import asyncio
import hashlib
import json
import time

from conftest import crear, esperar_estado


def hash_esperado(texto, n):
    h = texto.encode()
    for _ in range(n):
        h = hashlib.sha256(h).digest()
    return h.hex()


async def corrutinas_en_reposo(c, esperado, limite=3.0):
    """Las corrutinas vivas vuelven al número de reposo (no quedan huérfanas)."""
    fin = time.monotonic() + limite
    while True:
        vivas = (await c.get('/estadisticas')).json()['corrutinas_vivas']
        if vivas <= esperado or time.monotonic() > fin:
            return vivas
        await asyncio.sleep(0.02)


# ---------------------------------------------------------------
# descargar
# ---------------------------------------------------------------

async def test_descargas_concurrentes_tardan_lo_que_la_mas_lenta(armar_api, lento):
    url, _ = lento
    urls = [f'{url}/demora/0.5'] * 10
    async with armar_api() as (c, _):
        con = await esperar_estado(c, await crear(c, 'descargar', {'urls': urls}))
        sec = await esperar_estado(c, await crear(c, 'descargar', {'urls': urls[:4],
                                                                    'secuencial': True}))
    assert con['estado'] == sec['estado'] == 'completada'
    assert con['resultado']['ok'] == 10
    assert con['resultado']['tiempo_total'] < 1.5            # ~0.5, no 5
    assert sec['resultado']['tiempo_total'] >= 2.0           # 4 x 0.5


async def test_descarga_informa_errores_por_url_sin_fallar(armar_api, lento):
    url, _ = lento
    async with armar_api() as (c, _):
        t = await esperar_estado(c, await crear(c, 'descargar', {'urls': [
            f'{url}/demora/0', f'{url}/no-existe', 'http://127.0.0.1:9/cerrado']}))
    d = t['resultado']['descargas']
    assert t['estado'] == 'completada'
    assert d[0]['estado_http'] == 200
    assert d[1]['estado_http'] == 404
    assert 'error' in d[2]
    assert t['resultado']['ok'] == 1 and t['resultado']['errores'] == 2


def corrutinas_de_la_tarea(tid):
    """Tasks vivas de esa tarea: el job (`tarea-<id>`) y sus descargas hijas.

    Se filtra porque en los tests el servidor lento corre en el MISMO event
    loop, y sus handlers (dormidos en su propia demora) también son tasks.
    """
    return [t for t in asyncio.all_tasks()
            if t.get_name() == f'tarea-{tid}'
            or 'Ejecutores.descargar' in t.get_coro().__qualname__]


def conexiones_del_cliente(app):
    return len(app.state.ejecutores.cliente._transport._pool.connections)


async def test_cancelar_descarga_a_mitad_libera_todo(armar_api, lento):
    url, abiertas = lento
    async with armar_api() as (c, app):
        tid = await crear(c, 'descargar', {'urls': [f'{url}/demora/10'] * 5})
        await esperar_estado(c, tid, estados=('ejecutando',))
        await asyncio.sleep(0.3)                    # que las 5 conexiones estén abiertas
        assert abiertas() == 5
        assert len(corrutinas_de_la_tarea(tid)) == 6   # el job y sus 5 descargas hijas
        assert conexiones_del_cliente(app) == 5

        r = await c.delete(f'/tareas/{tid}')
        assert r.json()['estado'] == 'cancelada'
        # Ni corrutinas huérfanas ni conexiones abiertas del lado del cliente
        assert corrutinas_de_la_tarea(tid) == []
        assert conexiones_del_cliente(app) == 0


# ---------------------------------------------------------------
# hashear
# ---------------------------------------------------------------

async def test_hash_correcto_en_procesos(armar_api):
    async with armar_api() as (c, _):
        # 600.000 iteraciones: tres bloques (250k + 250k + 100k)
        t = await esperar_estado(c, await crear(c, 'hashear', {'texto': 'tp2', 'iteraciones': 600_000}))
    assert t['estado'] == 'completada'
    assert t['resultado']['hash'] == hash_esperado('tp2', 600_000)
    assert t['progreso'] == 1.0


async def test_hash_en_procesos_no_bloquea_el_event_loop(armar_api):
    async with armar_api() as (c, _):
        tid = await crear(c, 'hashear', {'texto': 'x', 'iteraciones': 2_000_000})
        await esperar_estado(c, tid, estados=('ejecutando',))
        peor = 0.0
        while (await c.get(f'/tareas/{tid}')).json()['estado'] == 'ejecutando':
            t0 = time.perf_counter()
            await asyncio.sleep(0.01)
            peor = max(peor, time.perf_counter() - t0 - 0.01)
        assert peor < 0.1, f'el loop se atraso {peor * 1000:.0f} ms'


async def test_hash_sin_executor_si_bloquea(armar_api):
    """El contraejemplo: con hash_executor='ninguno' el loop queda congelado."""
    async with armar_api(hash_executor='ninguno') as (c, _):
        tid = await crear(c, 'hashear', {'texto': 'x', 'iteraciones': 1_000_000})
        t0 = time.perf_counter()
        await asyncio.sleep(0.01)             # le toca al worker: arranca el hash
        await asyncio.sleep(0.01)             # esto recién vuelve cuando el hash termina
        atraso = time.perf_counter() - t0
        t = await esperar_estado(c, tid)
    assert atraso >= 0.8 * t['duracion'] > 0.1


async def test_cancelar_hash_libera_el_proceso(armar_api):
    async with armar_api(procesos=1) as (c, _):
        grande = await crear(c, 'hashear', {'texto': 'g', 'iteraciones': 100_000_000})
        await esperar_estado(c, grande, estados=('ejecutando',))
        await asyncio.sleep(0.3)
        r = await c.delete(f'/tareas/{grande}')
        assert r.json()['estado'] == 'cancelada'
        assert r.json()['progreso'] < 0.1
        # El único proceso del pool queda libre en menos de un bloque
        t0 = time.perf_counter()
        chico = await esperar_estado(c, await crear(c, 'hashear', {'texto': 'c', 'iteraciones': 1000}))
        assert chico['estado'] == 'completada'
        assert time.perf_counter() - t0 < 1.0


# ---------------------------------------------------------------
# cancelación, timeouts y robustez
# ---------------------------------------------------------------

async def test_cancelar_en_cola_no_llega_a_ejecutarse(armar_api):
    async with armar_api(workers=1) as (c, _):
        await crear(c, 'esperar', {'segundos': 0.5})
        segunda = await crear(c, 'esperar', {'segundos': 0.1})
        r = await c.delete(f'/tareas/{segunda}')
        assert r.json()['estado'] == 'cancelada'
        await esperar_estado(c, 1)
        await asyncio.sleep(0.2)
        t = (await c.get(f'/tareas/{segunda}')).json()
        assert t['estado'] == 'cancelada' and t['iniciada'] is None


async def test_cancelar_en_ejecucion_no_mata_al_worker(armar_api):
    async with armar_api(workers=1) as (c, _):
        reposo = (await c.get('/estadisticas')).json()['corrutinas_vivas']
        tid = await crear(c, 'esperar', {'segundos': 30})
        await esperar_estado(c, tid, estados=('ejecutando',))
        t0 = time.perf_counter()
        r = await c.delete(f'/tareas/{tid}')
        assert time.perf_counter() - t0 < 0.5
        assert r.json()['estado'] == 'cancelada'
        assert r.json()['error'] == 'cancelada durante la ejecucion'
        # El mismo (y único) worker sigue atendiendo
        otra = await esperar_estado(c, await crear(c, 'esperar', {'segundos': 0}))
        assert otra['estado'] == 'completada' and otra['worker'] == 0
        assert await corrutinas_en_reposo(c, reposo) == reposo


async def test_timeout_pasa_a_fallida(armar_api, lento):
    url, _ = lento
    async with armar_api() as (c, _):
        e = await esperar_estado(c, await crear(c, 'esperar', {'segundos': 5}, timeout=0.3))
        d = await esperar_estado(c, await crear(c, 'descargar', {'urls': [f'{url}/demora/5']},
                                                timeout=0.3))
        h = await esperar_estado(c, await crear(c, 'hashear', {'texto': 'h', 'iteraciones': 50_000_000},
                                                timeout=0.5))
    for t in (e, d, h):
        assert t['estado'] == 'fallida'
        assert t['error'].startswith('timeout')
    assert e['duracion'] < 1 and d['duracion'] < 1 and h['duracion'] < 1.5


async def test_timeout_por_defecto_del_servidor(armar_api):
    async with armar_api(timeout_defecto=0.2) as (c, _):
        t = await esperar_estado(c, await crear(c, 'esperar', {'segundos': 5}))
    assert t['estado'] == 'fallida' and t['timeout'] == 0.2


async def test_excepcion_en_la_tarea_la_marca_fallida(armar_api):
    async with armar_api(workers=1) as (c, app):
        async def explota(tarea):
            raise RuntimeError('algo salio mal')
        app.state.pool.ejecutores['esperar'] = explota
        t = await esperar_estado(c, await crear(c, 'esperar', {'segundos': 1}))
        assert t['estado'] == 'fallida'
        assert t['error'] == 'RuntimeError: algo salio mal'
        # El worker sobrevivió: hashear sigue andando
        h = await esperar_estado(c, await crear(c, 'hashear', {'texto': 'a', 'iteraciones': 10}))
        assert h['estado'] == 'completada'


async def test_worker_que_muere_por_un_bug_se_relanza(armar_api):
    async with armar_api(workers=1) as (c, app):
        pool = app.state.pool
        original = pool._ejecutar
        llamadas = []

        async def con_bug(tarea, i):
            llamadas.append(tarea.id)
            if len(llamadas) == 1:
                raise KeyError('bug en el worker, no en la tarea')
            await original(tarea, i)

        pool._ejecutar = con_bug
        await crear(c, 'esperar', {'segundos': 0})       # mata al worker
        await asyncio.sleep(0.1)
        t = await esperar_estado(c, await crear(c, 'esperar', {'segundos': 0}))
        assert t['estado'] == 'completada'
        assert len(pool.workers) == 1 and not pool.workers[0].done()


async def test_sin_lock_no_se_pierden_cuentas(armar_api):
    """200 tareas cortas con 20 workers: el contador por estado cierra exacto."""
    async with armar_api(workers=20, max_cola=500) as (c, _):
        await asyncio.gather(*(crear(c, 'esperar', {'segundos': 0.01}) for _ in range(200)))
        for tid in range(1, 201):
            await esperar_estado(c, tid)
        e = (await c.get('/estadisticas')).json()
    assert e['por_estado']['completada'] == 200 and e['total'] == 200


# ---------------------------------------------------------------
# apagado ordenado
# ---------------------------------------------------------------

async def test_apagado_espera_cancela_y_vuelca(armar_api, tmp_path):
    async with armar_api(workers=2, gracia_apagado=0.5) as (c, app):
        corta = await crear(c, 'esperar', {'segundos': 0.2})
        larga = await crear(c, 'esperar', {'segundos': 30})
        en_cola = await crear(c, 'esperar', {'segundos': 1})
        await esperar_estado(c, larga, estados=('ejecutando',))
        t0 = time.perf_counter()
    # al salir del `async with` corrió el shutdown del lifespan
    assert time.perf_counter() - t0 < 2
    volcados = list((tmp_path / 'estado').glob('estado_*.json'))
    assert len(volcados) == 1
    estados = {t['id']: t for t in json.loads(volcados[0].read_text())['tareas']}
    assert estados[corta]['estado'] == 'completada'           # terminó dentro de la gracia
    assert estados[larga]['estado'] == 'cancelada'            # no llegó: se cancela
    assert 'apagado' in estados[larga]['error']
    assert estados[en_cola]['estado'] == 'pendiente'          # no se arranca al apagar


async def test_al_apagar_no_acepta_tareas(armar_api):
    async with armar_api() as (c, app):
        app.state.pool.aceptando = False          # lo que hace el manejador de señal
        r = await c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 1}})
        assert r.status_code == 503


async def test_al_arrancar_informa_el_volcado_previo(armar_api, caplog):
    async with armar_api() as (c, _):
        await crear(c, 'esperar', {'segundos': 30})
    caplog.clear()
    with caplog.at_level('INFO', logger='tp2.persistencia'):
        async with armar_api():
            pass
    assert 'volcado previo encontrado' in caplog.text
