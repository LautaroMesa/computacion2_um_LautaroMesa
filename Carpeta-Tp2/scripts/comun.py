"""Funciones compartidas por los scripts de medición (clientes de la API)."""
import asyncio
import statistics
import time

import httpx

API = 'http://127.0.0.1:8000'   # 127.0.0.1 y no localhost: en Windows, localhost
                                 # prueba primero IPv6 y cada conexión tarda 0,2 s más


async def crear(cliente, tipo, parametros, timeout=None):
    cuerpo = {'tipo': tipo, 'parametros': parametros}
    if timeout:
        cuerpo['timeout'] = timeout
    r = await cliente.post('/tareas', json=cuerpo)
    r.raise_for_status()
    return r.json()['id']


async def esperar_fin(cliente, tarea_id, cada=0.05):
    while True:
        t = (await cliente.get(f'/tareas/{tarea_id}')).json()
        if t['estado'] in ('completada', 'fallida', 'cancelada'):
            return t
        await asyncio.sleep(cada)


async def esperar_todas(cliente, cada=0.1):
    """Hasta que no quede nada pendiente ni ejecutando."""
    while True:
        e = (await cliente.get('/estadisticas')).json()
        if e['por_estado']['pendiente'] == 0 and e['por_estado']['ejecutando'] == 0:
            return e
        await asyncio.sleep(cada)


async def estadisticas(cliente):
    return (await cliente.get('/estadisticas')).json()


def nuevo_cliente(api=API, **kw):
    kw.setdefault('timeout', 120)
    return httpx.AsyncClient(base_url=api, **kw)


def resumen_ms(muestras):
    """p50, p95 y máximo, en milisegundos."""
    if not muestras:
        return {'n': 0, 'p50': None, 'p95': None, 'max': None}
    ordenadas = sorted(muestras)
    p95 = ordenadas[min(len(ordenadas) - 1, int(len(ordenadas) * 0.95))]
    return {
        'n': len(muestras),
        'p50': round(statistics.median(ordenadas) * 1000, 1),
        'p95': round(p95 * 1000, 1),
        'max': round(ordenadas[-1] * 1000, 1),
    }


class Reloj:
    def __enter__(self):
        self.inicio = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.segundos = time.perf_counter() - self.inicio
