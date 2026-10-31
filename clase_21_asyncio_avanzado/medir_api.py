#!/usr/bin/env python3
"""Preguntas 13-15: cuánto tarda GET /tareas mientras la API está hasheando.

Manda un POST /hashear y, mientras se procesa, pide GET /tareas cada 100 ms
y anota cuánto tarda cada respuesta.

Uso (con api.py corriendo):
    python3 medir_api.py directo
    python3 medir_api.py executor
"""
import asyncio
import statistics
import sys
import time

import httpx

URL = 'http://127.0.0.1:8000'


async def main(modo):
    async with httpx.AsyncClient(base_url=URL, timeout=60) as cliente:
        await cliente.get('/tareas')                 # abrir la conexión antes
        hash_ = asyncio.create_task(cliente.post('/hashear', params={'modo': modo}))
        await asyncio.sleep(0.3)                     # que el cálculo ya esté corriendo

        tiempos = []
        async with httpx.AsyncClient(base_url=URL, timeout=60) as otro:
            while not hash_.done():
                t0 = time.perf_counter()
                await otro.get('/tareas')
                tiempos.append((time.perf_counter() - t0) * 1000)
                await asyncio.sleep(0.1)

        r = (await hash_).json()
        print(f'modo={modo}: el hash tardó {r["segundos"]} s')
        print(f'  GET /tareas durante el cálculo: {len(tiempos)} pedidos, '
              f'mediana {statistics.median(tiempos):.1f} ms, '
              f'peor {max(tiempos):.1f} ms')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else 'executor'))
