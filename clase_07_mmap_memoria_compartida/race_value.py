#!/usr/bin/env python3
"""5.1 — Race condition con Value.

4 procesos incrementan el mismo Value N veces cada uno. `contador.value += 1`
no es atomico: es leer, sumar y escribir. Si dos procesos leen el mismo valor
antes de que alguno escriba, uno de los dos incrementos se pierde.

Al final se corre lo mismo protegido con el lock que ya trae el Value
(get_lock()), para comparar resultado y tiempo.

Uso:
    python3 race_value.py [N]
"""
import sys
import time
from multiprocessing import Process, Value

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
NUM_PROCESOS = 4


def incrementar(contador, n, nombre):
    print(f"[{nombre}] Iniciando {n} incrementos...")
    for _ in range(n):
        contador.value += 1
    print(f"[{nombre}] Terminado")


def incrementar_con_lock(contador, n, nombre):
    for _ in range(n):
        with contador.get_lock():
            contador.value += 1


def correr(target, contador):
    procesos = [Process(target=target, args=(contador, N, f"P{i}"))
                for i in range(NUM_PROCESOS)]
    inicio = time.time()
    for p in procesos:
        p.start()
    for p in procesos:
        p.join()
    return time.time() - inicio


if __name__ == "__main__":
    esperado = NUM_PROCESOS * N

    contador = Value('i', 0)
    t = correr(incrementar, contador)
    print("\n--- Sin lock ---")
    print(f"Esperado: {esperado}")
    print(f"Obtenido: {contador.value}")
    print(f"Diferencia: {esperado - contador.value} (incrementos perdidos)")
    print(f"Tiempo: {t:.2f}s")

    contador = Value('i', 0)
    t = correr(incrementar_con_lock, contador)
    print("\n--- Con get_lock() ---")
    print(f"Esperado: {esperado}")
    print(f"Obtenido: {contador.value}")
    print(f"Diferencia: {esperado - contador.value}")
    print(f"Tiempo: {t:.2f}s")
