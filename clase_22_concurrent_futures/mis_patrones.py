#!/usr/bin/env python3
"""Lo que el ejercicio 2 pide implementar y patrones.py no trae.

Uso:
    python3 mis_patrones.py calculada   # pregunta 2: cuándo se calculó y cuándo se entregó
    python3 mis_patrones.py urls        # pregunta 10: el patrón del dict con 5 URLs
    python3 mis_patrones.py hashable    # pregunta 11: por qué un Future sirve de clave
    python3 mis_patrones.py wait        # preguntas 12-13: FIRST_COMPLETED / FIRST_EXCEPTION
    python3 mis_patrones.py primero     # pregunta 14: tres servidores, gana el primero
"""
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import (ALL_COMPLETED, FIRST_COMPLETED, FIRST_EXCEPTION,
                                ThreadPoolExecutor, as_completed, wait)

TRABAJOS = [('lenta', 0.5), ('rapida', 0.1), ('media', 0.2), ('otra', 0.4)]
T0 = 0.0


def tarea(nombre, demora):
    time.sleep(demora)
    # anota cuándo terminó DE VERDAD el cálculo, en el thread del pool
    return nombre, time.perf_counter() - T0


def calculada():
    global T0
    print('map(): cuándo se CALCULÓ cada una y cuándo me la ENTREGÓ map\n')
    with ThreadPoolExecutor(4) as pool:
        T0 = time.perf_counter()
        for nombre, listo in pool.map(tarea, *zip(*TRABAJOS)):
            entregado = time.perf_counter() - T0
            print(f'  {nombre:<7} calculada a los {listo:.2f}s, '
                  f'entregada a los {entregado:.2f}s '
                  f'(esperó {entregado - listo:.2f}s)')

    print('\nas_completed(): lo mismo\n')
    with ThreadPoolExecutor(4) as pool:
        T0 = time.perf_counter()
        futuros = [pool.submit(tarea, n, d) for n, d in TRABAJOS]
        for f in as_completed(futuros):
            nombre, listo = f.result()
            entregado = time.perf_counter() - T0
            print(f'  {nombre:<7} calculada a los {listo:.2f}s, '
                  f'entregada a los {entregado:.2f}s '
                  f'(esperó {entregado - listo:.2f}s)')


URLS = [
    'https://example.com/',
    'https://www.python.org/',
    'https://httpbin.org/status/404',
    'https://esto-no-existe.invalid/',
    'https://httpbin.org/delay/1',
]


def estado_http(url):
    """Devuelve el código HTTP. Deja escapar las excepciones de red."""
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code            # 4xx/5xx: el servidor respondió, no es una falla de red


def urls():
    print(f'{len(URLS)} URLs con as_completed y el dict {{future: url}}\n')
    t0 = time.perf_counter()
    with ThreadPoolExecutor(5) as pool:
        futuros = {pool.submit(estado_http, u): u for u in URLS}
        for f in as_completed(futuros):
            url = futuros[f]                         # de qué entrada era
            try:
                codigo = f.result()
                print(f'  {time.perf_counter() - t0:5.2f}s  {codigo}  {url}')
            except Exception as e:
                print(f'  {time.perf_counter() - t0:5.2f}s  FALLÓ {url}: '
                      f'{type(e).__name__}: {e}')


def hashable():
    with ThreadPoolExecutor(1) as pool:
        a = pool.submit(tarea, 'a', 0)
        b = pool.submit(tarea, 'a', 0)
        a.result(), b.result()
    print(f'  hash(a) = {hash(a)}   id(a) = {id(a)}   id(a) // 16 = {id(a) // 16}')
    print(f'  type(a).__hash__ is object.__hash__ -> {type(a).__hash__ is object.__hash__}')
    print(f'  type(a).__eq__   is object.__eq__   -> {type(a).__eq__ is object.__eq__}')
    print(f'  a == b -> {a == b}  (mismos argumentos, mismo resultado, distinto Future)')


def fallar(nombre, demora):
    time.sleep(demora)
    raise ValueError(f'{nombre} explotó')


def wait_modos():
    trabajos = [(tarea, 'lenta', 0.6), (fallar, 'rota', 0.2), (tarea, 'rapida', 0.1)]
    for modo in (FIRST_COMPLETED, FIRST_EXCEPTION, ALL_COMPLETED):
        with ThreadPoolExecutor(3) as pool:
            futuros = {pool.submit(fn, n, d): n for fn, n, d in trabajos}
            t0 = time.perf_counter()
            listos, pendientes = wait(futuros, return_when=modo)
            print(f'{modo:<16} volvió a los {time.perf_counter() - t0:.2f}s  '
                  f'listos={sorted(futuros[f] for f in listos)}  '
                  f'pendientes={sorted(futuros[f] for f in pendientes)}')


def consultar(servidor, demora):
    """Simula un servidor que tarda `demora` en contestar."""
    time.sleep(demora)
    return f'respuesta de {servidor}'


def primero():
    servidores = [('espejo-ar', 0.8), ('espejo-br', 0.3), ('espejo-us', 1.5)]
    t0 = time.perf_counter()
    pool = ThreadPoolExecutor(3)
    futuros = {pool.submit(consultar, s, d): s for s, d in servidores}
    listos, pendientes = wait(futuros, return_when=FIRST_COMPLETED)
    ganador = listos.pop()
    print(f'  a los {time.perf_counter() - t0:.2f}s ganó {futuros[ganador]}: '
          f'{ganador.result()!r}')
    for f in pendientes:
        print(f'  cancel() de {futuros[f]}: {f.cancel()}  (ya estaba corriendo: {f.running()})')
    # wait=False: no me quedo esperando a los perdedores para seguir trabajando
    pool.shutdown(wait=False, cancel_futures=True)
    print(f'  sigo trabajando a los {time.perf_counter() - t0:.2f}s, '
          'los perdedores terminan solos de fondo')


if __name__ == '__main__':
    modos = {'calculada': calculada, 'urls': urls, 'hashable': hashable,
             'wait': wait_modos, 'primero': primero}
    modo = sys.argv[1] if len(sys.argv) > 1 else ''
    if modo in modos:
        modos[modo]()
    else:
        print(__doc__)
