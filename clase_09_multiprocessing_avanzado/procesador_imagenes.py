#!/usr/bin/env python3
"""Procesador de imagenes paralelo.

Aplica un blur 3x3 a varias "imagenes" (matrices de enteros) primero en
serie y despues con Pool.map, y compara tiempos. Ademas verifica que los
dos caminos den exactamente los mismos resultados: un speedup no sirve de
nada si el resultado paralelo esta mal.

Uso:
    python3 procesador_imagenes.py [-n IMAGENES] [-s TAMANIO] [-w WORKERS]
"""
import argparse
import os
import random
import time
from multiprocessing import Pool


def crear_imagen(size):
    """Crea una 'imagen' como lista de listas de pixeles 0-255."""
    return [[random.randint(0, 255) for _ in range(size)]
            for _ in range(size)]


def aplicar_filtro(imagen):
    """Blur 3x3: cada pixel pasa a ser el promedio de su vecindario.
    Los bordes quedan en 0 (no tienen los 8 vecinos)."""
    size = len(imagen)
    resultado = [[0] * size for _ in range(size)]

    for i in range(1, size - 1):
        for j in range(1, size - 1):
            suma = 0
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    suma += imagen[i + di][j + dj]
            resultado[i][j] = suma // 9

    return resultado


def procesar_imagen(args):
    """Procesa una imagen y devuelve (idx, duracion, checksum, pid).
    Devuelvo un checksum y no la matriz entera para no pagar el costo de
    serializarla de vuelta al padre (pickle por el pipe del Pool)."""
    idx, imagen = args
    inicio = time.time()
    resultado = aplicar_filtro(imagen)
    duracion = time.time() - inicio
    return idx, duracion, sum(sum(fila) for fila in resultado), os.getpid()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('-n', '--imagenes', type=int, default=8)
    parser.add_argument('-s', '--size', type=int, default=100)
    parser.add_argument('-w', '--workers', type=int, default=4)
    args = parser.parse_args()

    print(f"CPUs disponibles: {os.cpu_count()}")
    print(f"Creando {args.imagenes} imagenes de {args.size}x{args.size}...")
    imagenes = [(i, crear_imagen(args.size)) for i in range(args.imagenes)]

    print("\nProcesamiento secuencial:")
    inicio = time.time()
    secuencial = [procesar_imagen(img) for img in imagenes]
    tiempo_secuencial = time.time() - inicio
    print(f"Tiempo: {tiempo_secuencial:.2f}s")

    print(f"\nProcesamiento paralelo ({args.workers} workers):")
    inicio = time.time()
    with Pool(args.workers) as pool:
        paralelo = pool.map(procesar_imagen, imagenes)
    tiempo_paralelo = time.time() - inicio

    for idx, duracion, checksum, pid in paralelo:
        print(f"  Imagen {idx}: {duracion:.3f}s  (worker pid {pid}, checksum {checksum})")
    print(f"Tiempo total: {tiempo_paralelo:.2f}s")

    # map conserva el orden de entrada, asi que se puede comparar posicion a posicion
    iguales = all(s[2] == p[2] for s, p in zip(secuencial, paralelo))
    speedup = tiempo_secuencial / tiempo_paralelo
    print(f"\nResultados iguales en serie y en paralelo: {'si' if iguales else 'NO'}")
    print(f"Speedup: {speedup:.2f}x")
    print(f"Eficiencia: {speedup / args.workers:.0%} (speedup / workers)")


if __name__ == "__main__":
    main()
