#!/usr/bin/env python3
"""5.2 — Calculo paralelo usando Array compartido.

Cada proceso escribe en una porcion distinta del Array, asi que no hay
race condition: ningun indice lo tocan dos procesos.
"""
import time
from multiprocessing import Array, Process

TAMANIO = 1000
NUM_PROCESOS = 4


def calcular_rango(resultado, inicio, fin):
    for i in range(inicio, fin):
        resultado[i] = i * i


if __name__ == "__main__":
    # lock=False: como las porciones no se pisan, el lock por elemento solo
    # agregaria costo sin proteger nada.
    resultado = Array('i', TAMANIO, lock=False)
    chunk = TAMANIO // NUM_PROCESOS

    inicio = time.time()
    procesos = []
    for i in range(NUM_PROCESOS):
        ini = i * chunk
        # el ultimo se lleva el resto si TAMANIO no es divisible
        fin = (i + 1) * chunk if i < NUM_PROCESOS - 1 else TAMANIO
        p = Process(target=calcular_rango, args=(resultado, ini, fin))
        p.start()
        procesos.append(p)

    for p in procesos:
        p.join()
    duracion = time.time() - inicio

    print(f"Calculo completado en {duracion:.4f}s")
    for i in (0, 10, 99, 999):
        print(f"resultado[{i}] = {resultado[i]}")

    errores = sum(1 for i in range(TAMANIO) if resultado[i] != i * i)
    print(f"Errores: {errores}")
