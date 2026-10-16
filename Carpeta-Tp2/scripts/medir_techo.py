#!/usr/bin/env python3
"""Medición 3: el techo del pool.

Manda N tareas `esperar` de S segundos de golpe (POST concurrentes) y mide:
  - cuántas aceptó (202) y cuántas rechazó por cola llena (503)
  - cuánto tardó en terminar todo, contra el ideal ceil(N / workers) * S
  - la latencia de GET /estadisticas mientras el servidor está cargado

Los POST se mandan con cliente_crudo (HTTP a mano con asyncio): con httpx
el cuello de botella era el propio cliente (~250 POST/s) y no el servidor.

Conviene correrlo DENTRO del contenedor, para no medir el reenvío de puertos
de Docker Desktop (en Windows suma ~8 ms por pedido):
    docker compose exec -w /app/scripts api python medir_techo.py --tareas 4,8,16,32,64
    TP2_WORKERS=20000 TP2_MAX_COLA=20000 docker compose up -d
    docker compose exec -w /app/scripts api python medir_techo.py --tareas 100,1000,10000 --segundos 2
"""
import argparse
import asyncio
import math
import time

from cliente_crudo import muchos_post
from comun import API, esperar_todas, estadisticas, nuevo_cliente, resumen_ms

CONEXIONES_POST = 50     # conexiones keep-alive mandando POST a la vez


async def sondear(cliente, parar, muestras):
    while not parar.is_set():
        t0 = time.perf_counter()
        await cliente.get('/estadisticas')
        muestras.append(time.perf_counter() - t0)
        await asyncio.sleep(0.2)


async def medir(api, n, segundos):
    async with nuevo_cliente(api) as cliente, nuevo_cliente(api) as sonda:
        workers = (await estadisticas(cliente))['workers_total']
        muestras, parar = [], asyncio.Event()
        tarea_sonda = asyncio.create_task(sondear(sonda, parar, muestras))

        t0 = time.perf_counter()
        cuerpo = {'tipo': 'esperar', 'parametros': {'segundos': segundos}, 'timeout': 3600}
        codigos = await muchos_post(api, '/tareas', cuerpo, n, CONEXIONES_POST)
        t_envio = time.perf_counter() - t0
        await esperar_todas(cliente)
        total = time.perf_counter() - t0

        parar.set()
        await tarea_sonda

    aceptadas = codigos.get(202, 0)
    ideal = math.ceil(aceptadas / workers) * segundos if aceptadas else 0
    lat = resumen_ms(muestras)
    return {'n': n, 'workers': workers, 'aceptadas': aceptadas,
            'rechazadas': codigos.get(503, 0), 'envio': t_envio, 'total': total,
            'ideal': ideal, 'lat_p50': lat['p50'], 'lat_max': lat['max']}


async def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--api', default=API)
    ap.add_argument('--tareas', default='4,8,16,32,64')
    ap.add_argument('--segundos', type=float, default=1.0)
    args = ap.parse_args()

    print(f'{"N":>6} {"workers":>7} {"acept.":>6} {"503":>6} {"envio":>7} '
          f'{"total":>8} {"ideal":>7} {"exceso":>7} {"GET p50":>8} {"GET max":>8}')
    for n in (int(x) for x in args.tareas.split(',')):
        r = await medir(args.api, n, args.segundos)
        exceso = r['total'] - r['ideal']
        print(f'{r["n"]:>6} {r["workers"]:>7} {r["aceptadas"]:>6} {r["rechazadas"]:>6} '
              f'{r["envio"]:>6.2f}s {r["total"]:>7.2f}s {r["ideal"]:>6.1f}s {exceso:>6.2f}s '
              f'{r["lat_p50"]:>6.1f}ms {r["lat_max"]:>6.1f}ms')


if __name__ == '__main__':
    asyncio.run(main())
