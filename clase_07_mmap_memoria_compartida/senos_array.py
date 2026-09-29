#!/usr/bin/env python3
"""Tarea del ejercicio 5: Array('d', 100) con sin(i * 0.01) en 4 procesos.

Bonus: cada proceso acumula la suma de sus resultados en un Value('d')
compartido. Se corre dos veces:
  - sin lock: cada proceso hace `suma.value += x` por cada elemento
  - con lock: igual pero dentro de `with suma.get_lock()`
y se compara contra la suma calculada por el padre.

Con 100 elementos casi nunca se ve la race (cada proceso termina antes de
que arranque el siguiente), asi que se puede subir el tamaño por argumento
para forzarla.

Uso:
    python3 senos_array.py [TAMANIO]
"""
import math
import sys
from multiprocessing import Array, Process, Value

TAMANIO = int(sys.argv[1]) if len(sys.argv) > 1 else 100
NUM_PROCESOS = 4


def calcular(resultado, suma, inicio, fin, usar_lock):
    for i in range(inicio, fin):
        x = math.sin(i * 0.01)
        resultado[i] = x
        if usar_lock:
            with suma.get_lock():
                suma.value += x
        else:
            suma.value += x


def correr(usar_lock):
    resultado = Array('d', TAMANIO, lock=False)
    suma = Value('d', 0.0)
    chunk = TAMANIO // NUM_PROCESOS

    procesos = []
    for i in range(NUM_PROCESOS):
        ini = i * chunk
        fin = (i + 1) * chunk if i < NUM_PROCESOS - 1 else TAMANIO
        p = Process(target=calcular, args=(resultado, suma, ini, fin, usar_lock))
        p.start()
        procesos.append(p)
    for p in procesos:
        p.join()
    return resultado, suma.value


if __name__ == "__main__":
    resultado, suma_sin_lock = correr(usar_lock=False)

    print(f"Primeros 20 resultados (de {TAMANIO}):")
    for i in range(20):
        print(f"  sin({i * 0.01:.2f}) = {resultado[i]:.6f}")

    errores = sum(1 for i in range(TAMANIO)
                  if not math.isclose(resultado[i], math.sin(i * 0.01)))
    print(f"Errores en el Array: {errores}")

    # La suma "verdadera", calculada en el padre sobre el Array ya lleno
    suma_real = math.fsum(resultado[:])
    _, suma_con_lock = correr(usar_lock=True)

    print(f"\nSuma esperada:     {suma_real:.6f}")
    print(f"Suma sin lock:     {suma_sin_lock:.6f}  "
          f"(diferencia {suma_real - suma_sin_lock:+.6f})")
    print(f"Suma con get_lock: {suma_con_lock:.6f}  "
          f"(diferencia {suma_real - suma_con_lock:+.6f})")
