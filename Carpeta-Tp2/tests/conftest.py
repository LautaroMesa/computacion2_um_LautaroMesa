"""Fixtures: la app real (con su lifespan) y un servidor HTTP lento local."""
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'scripts'))

from app.config import Config  # noqa: E402
from app.main import crear_app  # noqa: E402
import servidor_lento  # noqa: E402

TERMINALES = ('completada', 'fallida', 'cancelada')


@pytest.fixture
def armar_api(tmp_path):
    """Fábrica: `async with armar_api(workers=1) as (cliente, app):`.

    Corre el lifespan de verdad (workers, pool de procesos, cliente HTTP) y
    habla con la app por ASGITransport, sin red.
    """
    @asynccontextmanager
    async def armar(**cambios):
        valores = dict(workers=2, procesos=1, max_cola=100, timeout_defecto=30,
                       gracia_apagado=2, dir_estado=tmp_path / 'estado',
                       hash_executor='proceso')
        valores.update(cambios)
        app = crear_app(Config(**valores))
        async with app.router.lifespan_context(app):
            transporte = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transporte, base_url='http://test') as c:
                yield c, app
    return armar


@pytest.fixture
async def lento():
    """Servidor lento en un puerto libre. Devuelve (url_base, conexiones_abiertas())."""
    abiertas = set()

    async def atender(reader, writer):
        abiertas.add(writer)
        try:
            await servidor_lento.atender(reader, writer)
        finally:
            abiertas.discard(writer)

    servidor = await asyncio.start_server(atender, '127.0.0.1', 0)
    puerto = servidor.sockets[0].getsockname()[1]
    async with servidor:
        yield f'http://127.0.0.1:{puerto}', lambda: len(abiertas)
        servidor.close()


async def crear(c, tipo, parametros, **extra):
    r = await c.post('/tareas', json={'tipo': tipo, 'parametros': parametros, **extra})
    assert r.status_code == 202, r.text
    return r.json()['id']


async def esperar_estado(c, tarea_id, estados=TERMINALES, limite=20.0):
    fin = asyncio.get_running_loop().time() + limite
    while True:
        t = (await c.get(f'/tareas/{tarea_id}')).json()
        if t['estado'] in estados:
            return t
        assert asyncio.get_running_loop().time() < fin, f'la tarea quedo en {t["estado"]}'
        await asyncio.sleep(0.02)
