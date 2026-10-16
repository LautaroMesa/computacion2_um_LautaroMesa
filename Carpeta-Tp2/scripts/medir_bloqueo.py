#!/usr/bin/env python3
"""Medición 2: el event loop bloqueado.

Manda un `hashear` pesado y, mientras corre, pide GET /tareas cada 50 ms y
mide cuánto tarda cada respuesta. Hay que correrlo una vez por modo del
servidor (la variable TP2_HASH_EXECUTOR de la API):

    TP2_HASH_EXECUTOR=ninguno docker compose up --build -d   # SIN executor
    python scripts/medir_bloqueo.py
    TP2_HASH_EXECUTOR=thread  docker compose up --build -d   # asyncio.to_thread
    python scripts/medir_bloqueo.py
    TP2_HASH_EXECUTOR=proceso docker compose up --build -d   # ProcessPoolExecutor
    python scripts/medir_bloqueo.py
"""
import argparse
import asyncio
import time

from comun import API, crear, esperar_fin, estadisticas, nuevo_cliente, resumen_ms

INTERVALO = 0.05


async def medir_get(cliente, muestras, parar):
    """GET /tareas uno por vez, cada INTERVALO, hasta que `parar` se active.
    El pedido que esté en vuelo cuando se active igual se cuenta: es
    justamente el que quedó atrapado detrás del cálculo."""
    while not parar.is_set():
        t0 = time.perf_counter()
        r = await cliente.get('/tareas', params={'limite': 10})
        r.raise_for_status()
        muestras.append(time.perf_counter() - t0)
        await asyncio.sleep(INTERVALO)


async def vigilar(cliente, tid, parar, final):
    while True:
        t = (await cliente.get(f'/tareas/{tid}')).json()
        if t['estado'] in ('completada', 'fallida', 'cancelada'):
            final.update(t)
            parar.set()
            return
        await asyncio.sleep(INTERVALO)


async def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--api', default=API)
    ap.add_argument('--iteraciones', type=int, default=6_000_000)
    ap.add_argument('--paralelo', type=int, default=0, metavar='N',
                    help='en vez de medir latencia: N hashes a la vez y el tiempo total')
    args = ap.parse_args()
    if args.paralelo:
        return await paralelo(args)

    # Tres clientes (tres conexiones): el que manda la tarea, el que vigila
    # cuándo termina y el que mide. Ninguno espera detrás de otro.
    async with nuevo_cliente(args.api) as control, nuevo_cliente(args.api) as medidor, \
            nuevo_cliente(args.api) as vigia:
        modo = (await estadisticas(control))['hash_executor']

        base, parar = [], asyncio.Event()
        tarea = asyncio.create_task(medir_get(medidor, base, parar))
        await asyncio.sleep(1.0)
        parar.set()
        await tarea

        tid = await crear(control, 'hashear', {'texto': 'medicion', 'iteraciones': args.iteraciones})
        t0 = time.perf_counter()
        durante, parar, final = [], asyncio.Event(), {}
        await asyncio.gather(medir_get(medidor, durante, parar),
                             vigilar(vigia, tid, parar, final))
        total = time.perf_counter() - t0

    b, d = resumen_ms(base), resumen_ms(durante)
    print(f'modo del servidor: TP2_HASH_EXECUTOR={modo}')
    print(f'hashear {args.iteraciones:,} iteraciones: {final["duracion"]:.2f}s de calculo '
          f'({total:.2f}s hasta verla terminada)')
    print(f'  GET /tareas en reposo:        p50 {b["p50"]:7.1f} ms   max {b["max"]:7.1f} ms   ({b["n"]} pedidos)')
    print(f'  GET /tareas durante el hash:  p50 {d["p50"]:7.1f} ms   max {d["max"]:7.1f} ms   ({d["n"]} pedidos)')


async def paralelo(args):
    """N hashes simultáneos: con threads el GIL los serializa, con procesos no."""
    async with nuevo_cliente(args.api) as c:
        e = await estadisticas(c)
        t0 = time.perf_counter()
        ids = await asyncio.gather(*(crear(c, 'hashear', {'texto': str(i), 'iteraciones': args.iteraciones})
                                     for i in range(args.paralelo)))
        finales = [await esperar_fin(c, i) for i in ids]
        total = time.perf_counter() - t0
    calculos = [t['duracion'] for t in finales]
    print(f'{args.paralelo} hashes de {args.iteraciones:,} a la vez, '
          f'TP2_HASH_EXECUTOR={e["hash_executor"]}, workers={e["workers_total"]}: '
          f'total {total:.2f}s (cada uno {min(calculos):.2f}-{max(calculos):.2f}s)')


if __name__ == '__main__':
    asyncio.run(main())
