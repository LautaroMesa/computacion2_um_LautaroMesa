#!/usr/bin/env python3
"""Ejercicio 5: tiempo de crear (y esperar) 100 procesos con cada metodo
de arranque.

set_start_method() solo se puede llamar una vez por programa, asi que uso
get_context(), que da lo mismo pero por contexto y permite medir los dos
(o tres, en Linux tambien forkserver) en la misma corrida.
"""
import sys
import time
import multiprocessing as mp

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100


def nada():
    pass


def medir(metodo):
    ctx = mp.get_context(metodo)
    inicio = time.time()
    procesos = [ctx.Process(target=nada) for _ in range(N)]
    for p in procesos:
        p.start()
    for p in procesos:
        p.join()
    return time.time() - inicio


if __name__ == "__main__":
    for metodo in mp.get_all_start_methods():
        t = medir(metodo)
        print(f"{metodo:>10}: {t:.3f}s para {N} procesos  ({t / N * 1000:.1f} ms c/u)")
