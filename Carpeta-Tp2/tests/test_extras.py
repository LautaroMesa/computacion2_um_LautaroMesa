"""Bonus: WebSocket /eventos y métricas Prometheus.

httpx no habla WebSocket, así que acá se usa el TestClient de Starlette, que
corre la app (y su lifespan) en un event loop propio.
"""
import asyncio

from fastapi.testclient import TestClient

from app.config import Config
from app.main import crear_app
from app.registro import CORTE, Registro


def armar(tmp_path, **cambios):
    valores = dict(workers=2, procesos=1, dir_estado=tmp_path / 'estado', hash_executor='thread')
    valores.update(cambios)
    return TestClient(crear_app(Config(**valores)))


def test_eventos_por_websocket(tmp_path):
    with armar(tmp_path) as c, c.websocket_connect('/eventos') as ws:
        r = c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 0.1}})
        tid = r.json()['id']
        estados = [ws.receive_json()['estado'] for _ in range(3)]
        assert estados == ['pendiente', 'ejecutando', 'completada']

        r = c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 30}})
        assert ws.receive_json()['estado'] == 'pendiente'
        assert ws.receive_json()['estado'] == 'ejecutando'
        c.delete(f'/tareas/{r.json()["id"]}')
        ultimo = ws.receive_json()
        assert ultimo['estado'] == 'cancelada' and ultimo['id'] == tid + 1


def test_websocket_desconectado_se_desuscribe(tmp_path):
    with armar(tmp_path) as c:
        registro = c.app.state.registro
        with c.websocket_connect('/eventos') as ws:
            c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 0}})
            ws.receive_json()
            assert len(registro._oyentes) == 1
        # Al cerrar el cliente, el handler sale de receive() y se da de baja.
        # (TestClient lo procesa en su propio loop; se le da un instante.)
        for _ in range(50):
            if not registro._oyentes:
                break
            c.get('/')
        assert len(registro._oyentes) == 0


async def test_suscriptor_lento_se_corta_sin_frenar_al_resto():
    registro = Registro()
    lento = registro.suscribir(capacidad=3)
    rapido = registro.suscribir(capacidad=100)
    for i in range(5):
        registro.crear('esperar', {'segundos': 0}, 1)
    assert lento.qsize() == 1 and lento.get_nowait() is CORTE      # cortado
    assert rapido.qsize() == 5                                     # recibió todo
    assert lento not in registro._oyentes
    await asyncio.sleep(0)


def test_metricas_prometheus(tmp_path):
    with armar(tmp_path, workers=1, max_cola=1) as c:
        c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 30}})
        c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 30}})
        c.post('/tareas', json={'tipo': 'esperar', 'parametros': {'segundos': 30}})
        r = c.get('/metrics')
        assert r.status_code == 200
        assert r.headers['content-type'].startswith('text/plain')
        texto = r.text
        assert '# TYPE tp2_tareas gauge' in texto
        assert 'tp2_workers 1' in texto
        assert 'tp2_tareas_rechazadas_total 1' in texto
        lineas = [l for l in texto.splitlines() if l and not l.startswith('#')]
        for l in lineas:                       # formato: nombre{etiquetas} valor
            nombre, valor = l.rsplit(' ', 1)
            float(valor)
