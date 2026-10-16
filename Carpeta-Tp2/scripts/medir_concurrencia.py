#!/usr/bin/env python3
"""Medición 1: 20 descargas secuenciales contra 20 concurrentes.

Tres formas de bajar las mismas N URLs:
  A. UNA tarea `descargar` con secuencial=true   (un for con await adentro)
  B. UNA tarea `descargar` concurrente            (TaskGroup: todas a la vez)
  C. N tareas de 1 URL cada una                   (las reparte el pool de workers)

Con la API levantada (docker compose up --build):
    python scripts/medir_concurrencia.py                          # servidor lento local
    python scripts/medir_concurrencia.py --internet               # URLs reales
"""
import argparse
import asyncio
import statistics

from comun import API, Reloj, crear, esperar_fin, esperar_todas, estadisticas, nuevo_cliente

URLS_INTERNET = [
    'https://example.com', 'https://www.python.org', 'https://docs.python.org/3/',
    'https://pypi.org', 'https://www.wikipedia.org', 'https://github.com',
    'https://www.um.edu.ar', 'https://fastapi.tiangolo.com', 'https://www.python-httpx.org',
    'https://www.debian.org', 'https://www.kernel.org', 'https://www.mozilla.org',
    'https://www.gnu.org', 'https://www.postgresql.org', 'https://nginx.org',
    'https://www.docker.com', 'https://www.rust-lang.org', 'https://go.dev',
    'https://www.ietf.org', 'https://www.w3.org',
]


async def una_tarea(cliente, urls, secuencial):
    with Reloj() as r:
        tid = await crear(cliente, 'descargar', {'urls': urls, 'secuencial': secuencial})
        t = await esperar_fin(cliente, tid)
    res = t['resultado']
    return {'pared': r.segundos, 'tarea': res['tiempo_total'], 'ok': res['ok'],
            'suma': res['suma_de_tiempos']}


async def n_tareas(cliente, urls):
    with Reloj() as r:
        ids = await asyncio.gather(*(crear(cliente, 'descargar', {'urls': [u]}) for u in urls))
        await esperar_todas(cliente)
    tareas = [(await cliente.get(f'/tareas/{i}')).json() for i in ids]
    ok = sum(t['resultado']['ok'] for t in tareas if t['resultado'])
    return {'pared': r.segundos, 'ok': ok}


async def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--api', default=API)
    ap.add_argument('--url', default='http://lento:8081/demora/1',
                    help='URL a repetir N veces (vista desde el contenedor de la API)')
    ap.add_argument('-n', type=int, default=20)
    ap.add_argument('--repeticiones', type=int, default=3)
    ap.add_argument('--internet', action='store_true', help='usar 20 sitios reales distintos')
    args = ap.parse_args()

    urls = URLS_INTERNET[:args.n] if args.internet else [args.url] * args.n
    async with nuevo_cliente(args.api) as cliente:
        e = await estadisticas(cliente)
        print(f'{args.n} descargas de {"sitios reales" if args.internet else args.url}  '
              f'(workers del pool: {e["workers_total"]})\n')
        filas = {'A secuencial (1 tarea)': [], 'B concurrente (1 tarea)': [],
                 f'C {args.n} tareas de 1 URL': []}
        for rep in range(1, args.repeticiones + 1):
            a = await una_tarea(cliente, urls, secuencial=True)
            b = await una_tarea(cliente, urls, secuencial=False)
            c = await n_tareas(cliente, urls)
            filas['A secuencial (1 tarea)'].append(a)
            filas['B concurrente (1 tarea)'].append(b)
            filas[f'C {args.n} tareas de 1 URL'].append(c)
            print(f'  corrida {rep}: A {a["tarea"]:6.2f}s   B {b["tarea"]:6.2f}s   '
                  f'C {c["pared"]:6.2f}s   (ok: {a["ok"]}/{b["ok"]}/{c["ok"]})')

    def media(clave, campo):
        return statistics.mean(x[campo] for x in filas[clave])

    sec = media('A secuencial (1 tarea)', 'tarea')
    con = media('B concurrente (1 tarea)', 'tarea')
    c_clave = f'C {args.n} tareas de 1 URL'
    print(f'\n  {"modo":<28} {"media":>8}')
    print(f'  {"A secuencial (1 tarea)":<28} {sec:7.2f}s')
    print(f'  {"B concurrente (1 tarea)":<28} {con:7.2f}s   speedup {sec / con:5.1f}x')
    print(f'  {c_clave:<28} {media(c_clave, "pared"):7.2f}s   '
          f'(limitado por los workers del pool)')
    print(f'\n  suma de los tiempos individuales en B: '
          f'{media("B concurrente (1 tarea)", "suma"):.2f}s  '
          f'-> B tarda lo que la mas lenta, no la suma')


if __name__ == '__main__':
    asyncio.run(main())
