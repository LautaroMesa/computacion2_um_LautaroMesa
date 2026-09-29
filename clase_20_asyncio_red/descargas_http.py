#!/usr/bin/env python3
"""Descargas HTTP reales con asyncio + httpx (partes B, C y D).

Modos:
    secuencial        una detras de otra (con await, pero sin concurrencia)
    gather            todas a la vez con asyncio.gather
    semaforo [N]      gather, pero como mucho N a la vez (default 3)
    cliente-por-url   gather creando un AsyncClient NUEVO por descarga
    requests          gather, pero con requests (sincronico) adentro de la corrutina
    fallos            una URL invalida en la lista: gather normal
    fallos-rx         lo mismo con gather(..., return_exceptions=True)
    muchas [N]        N descargas sin semaforo y sin limite del pool de httpx

Uso:
    python3 descargas_http.py MODO [N] [--url URL] [--cantidad K]
"""
import argparse
import asyncio
import time

import httpx

URL = 'https://example.com'


async def bajar(cliente, url):
    r = await cliente.get(url)
    return url, r.status_code, len(r.content)


async def secuencial(urls):
    async with httpx.AsyncClient(timeout=10) as cliente:
        return [await bajar(cliente, u) for u in urls]


async def concurrente(urls, return_exceptions=False):
    # El cliente se crea UNA vez y lo comparten todas las descargas: mantiene
    # un pool de conexiones abiertas (keep-alive) y reutiliza las que ya
    # hicieron el handshake TCP + TLS.
    async with httpx.AsyncClient(timeout=10) as cliente:
        return await asyncio.gather(*(bajar(cliente, u) for u in urls),
                                    return_exceptions=return_exceptions)


async def con_semaforo(urls, limite):
    sem = asyncio.Semaphore(limite)
    activas = maximo = 0

    async with httpx.AsyncClient(timeout=10) as cliente:
        async def acotada(url):
            nonlocal activas, maximo
            async with sem:
                activas += 1
                maximo = max(maximo, activas)
                try:
                    return await bajar(cliente, url)
                finally:
                    activas -= 1

        resultados = await asyncio.gather(*(acotada(u) for u in urls))
    print(f'  (maximo de descargas simultaneas observado: {maximo})')
    return resultados


async def cliente_por_url(urls):
    async def bajar_con_cliente_propio(url):
        async with httpx.AsyncClient(timeout=10) as cliente:
            return await bajar(cliente, url)
    return await asyncio.gather(*(bajar_con_cliente_propio(u) for u in urls))


async def con_requests(urls):
    import requests

    async def bajar_bloqueante(url):
        r = requests.get(url, timeout=10)      # bloquea el event loop entero
        return url, r.status_code, len(r.content)
    return await asyncio.gather(*(bajar_bloqueante(u) for u in urls))


async def fallos_sin_rx(urls):
    """gather normal con una URL invalida: que le pasa a las DEMAS."""
    terminadas = []

    async def bajar_y_anotar(cliente, url):
        r = await bajar(cliente, url)
        terminadas.append(time.perf_counter())
        return r

    async with httpx.AsyncClient(timeout=10) as cliente:
        tareas = [asyncio.ensure_future(bajar_y_anotar(cliente, u)) for u in urls]
        t0 = time.perf_counter()
        try:
            await asyncio.gather(*tareas)
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f'  gather lanzo {type(e).__name__} a los {dt:.2f}s: {e}')
            print(f'  en ese momento: {len(terminadas)} terminadas, '
                  f'{sum(not t.done() for t in tareas)} todavia corriendo')
            await asyncio.sleep(3)             # ¿siguen o las cancelo gather?
            print(f'  3s despues: {len(terminadas)} terminadas, '
                  f'{sum(t.cancelled() for t in tareas)} canceladas '
                  '-> gather NO cancela a las demas, pero sus resultados se pierden')
    return []


async def muchas(urls):
    # Sin limite en el pool: httpx por defecto acota a 100 conexiones, lo que
    # ya es una forma de semaforo. Aca se lo sacamos para ver el problema.
    limites = httpx.Limits(max_connections=None, max_keepalive_connections=None)
    async with httpx.AsyncClient(timeout=30, limits=limites) as cliente:
        return await asyncio.gather(*(bajar(cliente, u) for u in urls),
                                    return_exceptions=True)


def resumir(resultados):
    ok = [r for r in resultados if isinstance(r, tuple)]
    errores = [r for r in resultados if isinstance(r, BaseException)]
    print(f'  ok: {len(ok)}  errores: {len(errores)}')
    for r in ok[:2]:
        print(f'    {r}')
    tipos = {}
    for e in errores:
        clave = f'{type(e).__name__}: {str(e)[:90]}'
        tipos[clave] = tipos.get(clave, 0) + 1
    for clave, n in tipos.items():
        print(f'    {n} x {clave}')


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('modo')
    ap.add_argument('n', nargs='?', type=int, default=None)
    ap.add_argument('--url', default=URL)
    ap.add_argument('--cantidad', type=int, default=10)
    args = ap.parse_args()
    urls = [args.url] * args.cantidad

    t0 = time.perf_counter()
    try:
        if args.modo == 'secuencial':
            resultados = await secuencial(urls)
        elif args.modo == 'gather':
            resultados = await concurrente(urls)
        elif args.modo == 'semaforo':
            resultados = await con_semaforo(urls, args.n or 3)
        elif args.modo == 'cliente-por-url':
            resultados = await cliente_por_url(urls)
        elif args.modo == 'requests':
            resultados = await con_requests(urls)
        elif args.modo == 'fallos':
            urls[3] = 'https://no-existe.invalid'
            resultados = await fallos_sin_rx(urls)
        elif args.modo == 'fallos-rx':
            urls[3] = 'https://no-existe.invalid'
            resultados = await concurrente(urls, return_exceptions=True)
        elif args.modo == 'muchas':
            resultados = await muchas([args.url] * (args.n or 200))
        else:
            raise SystemExit(f'modo desconocido: {args.modo}')
    except Exception as e:
        print(f'  {args.modo}: EXCEPCION {type(e).__name__}: {e}  '
              f'({time.perf_counter() - t0:.2f}s)')
        return
    dt = time.perf_counter() - t0
    print(f'  {args.modo}: {dt:.2f}s')
    resumir(resultados)


if __name__ == '__main__':
    asyncio.run(main())
