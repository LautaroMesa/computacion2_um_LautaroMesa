#!/usr/bin/env python3
"""Ejercicio 2: 5 procesos que duermen entre 0.5 y 2 s. El tiempo total
tiene que ser el del mas lento, no la suma."""
import random
import time
from multiprocessing import Process


def worker(i, espera):
    time.sleep(espera)
    print(f"worker {i} termino ({espera:.2f}s)")


if __name__ == "__main__":
    esperas = [random.uniform(0.5, 2) for _ in range(5)]
    procesos = [Process(target=worker, args=(i, e)) for i, e in enumerate(esperas)]

    inicio = time.time()
    for p in procesos:
        p.start()
    for p in procesos:
        p.join()
    total = time.time() - inicio

    print(f"\nTiempo total:            {total:.2f}s")
    print(f"Mas lento:               {max(esperas):.2f}s")
    print(f"Suma (si fuera en serie): {sum(esperas):.2f}s")
