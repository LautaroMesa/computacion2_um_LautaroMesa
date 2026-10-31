#!/usr/bin/env python3
"""Las preguntas 7 a 10 del ejercicio 3, que executor.py no cubre.

Uso:
    python3 executor_extra.py uno       # 1 tarea CPU-bound: threads vs procesos
    python3 executor_extra.py io        # 4 tareas con time.sleep: threads vs procesos
    python3 executor_extra.py lambda    # pasarle una lambda al ProcessPoolExecutor
    python3 executor_extra.py grande    # costo de mandar un argumento grande
"""
import asyncio
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from executor import hashear   # el mismo trabajo de ~5 s de la cátedra


def dormir(segundos=2):
    """I/O bloqueante simulado: el thread suelta el GIL mientras duerme."""
    time.sleep(segundos)
    return segundos


def largo(datos):
    """Trabajo casi nulo: lo que se mide es el viaje del argumento."""
    return len(datos) if hasattr(datos, '__len__') else datos


async def threads_contra_procesos(funcion, n, titulo):
    print(f'{titulo}\n')
    t0 = time.perf_counter()
    await asyncio.gather(*(asyncio.to_thread(funcion) for _ in range(n)))
    con_threads = time.perf_counter() - t0
    print(f'  asyncio.to_thread (threads)      {con_threads:5.2f}s')

    with ProcessPoolExecutor(max_workers=n) as pool:
        loop = asyncio.get_running_loop()
        # un viaje vacío para que el arranque de los procesos no entre en la cuenta
        await asyncio.gather(*(loop.run_in_executor(pool, largo, 0) for _ in range(n)))
        t0 = time.perf_counter()
        await asyncio.gather(*(loop.run_in_executor(pool, funcion) for _ in range(n)))
        con_procesos = time.perf_counter() - t0
    print(f'  ProcessPoolExecutor (procesos)   {con_procesos:5.2f}s')
    print(f'\n  Relación threads/procesos: {con_threads / con_procesos:.2f}x')


async def con_lambda():
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=1) as pool:
        try:
            await loop.run_in_executor(pool, lambda: 2 + 2)
        except Exception as e:
            print(f'  {type(e).__module__}.{type(e).__name__}: {e}')
        # con un thread la misma lambda anda: no hay que serializar nada
        r = await asyncio.to_thread(lambda: 2 + 2)
        print(f'  la misma lambda con asyncio.to_thread devuelve: {r}')


async def argumento_grande():
    loop = asyncio.get_running_loop()
    lista = list(range(1_000_000))
    with ProcessPoolExecutor(max_workers=1) as pool:
        await loop.run_in_executor(pool, largo, 0)          # calentar el pool
        for etiqueta, arg in (('un número', 42), ('lista de 1.000.000', lista)):
            veces = 20
            t0 = time.perf_counter()
            for _ in range(veces):
                await loop.run_in_executor(pool, largo, arg)
            ms = (time.perf_counter() - t0) / veces * 1000
            print(f'  {etiqueta:<20} {ms:8.2f} ms por llamada')

    t0 = time.perf_counter()
    for _ in range(20):
        await asyncio.to_thread(largo, lista)
    ms = (time.perf_counter() - t0) / 20 * 1000
    print(f'  {"(thread, la lista)":<20} {ms:8.2f} ms por llamada')


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else ''
    if modo == 'uno':
        asyncio.run(threads_contra_procesos(hashear, 1, '1 sola tarea CPU-bound:'))
    elif modo == 'io':
        asyncio.run(threads_contra_procesos(dormir, 4, '4 tareas con time.sleep(2):'))
    elif modo == 'lambda':
        asyncio.run(con_lambda())
    elif modo == 'grande':
        asyncio.run(argumento_grande())
    else:
        print(__doc__)
