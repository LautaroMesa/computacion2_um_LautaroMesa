# Clase 9 — Multiprocessing avanzado

Ejercicio obligatorio 5: procesador de imágenes paralelo con `Pool.map`.

## Qué hace

`procesador_imagenes.py` genera N "imágenes" (matrices de enteros 0-255) y les
aplica un blur 3x3. Primero lo hace en serie y después con `Pool(workers).map`;
muestra el tiempo de cada una, el speedup y la eficiencia (speedup / workers).

Agregué dos cosas a la consigna:

- **Verificación de resultados**: compara el checksum de cada imagen entre la
  versión en serie y la paralela. Un speedup no sirve si el resultado paralelo
  está mal. `map` devuelve los resultados en el mismo orden de entrada, así que
  se comparan posición por posición.
- **Parámetros** (`-n`, `-s`, `-w`) para ver cómo cambia el speedup según el tamaño
  del trabajo y la cantidad de workers.

El worker devuelve el checksum y no la matriz filtrada: devolver la matriz
implica serializarla con pickle y mandarla al padre por el pipe del Pool, y eso es
overhead que no aporta nada a la medición.

## Cómo correr

```bash
docker build -t clase9 .
docker run --rm clase9 python procesador_imagenes.py                    # 8 imágenes de 100x100, 4 workers
docker run --rm clase9 python procesador_imagenes.py -n 32 -s 400 -w 8
```

## Resultados (Linux/WSL2, 16 CPUs)

### Caso de la consigna: 8 imágenes de 100x100, 4 workers

```
Procesamiento secuencial:
Tiempo: 0.04s

Procesamiento paralelo (4 workers):
  Imagen 0: 0.006s  (worker pid 1344, checksum 1219747)
  ...
Tiempo total: 0.05s

Resultados iguales en serie y en paralelo: si
Speedup: 0.80x
```

**El paralelo es más lento.** Cada imagen tarda ~5 ms, y crear 4 procesos,
serializar las imágenes y mandarlas por pipes cuesta más que eso. Paralelizar
conviene recién cuando cada tarea es bastante más cara que el overhead de repartirla.

### Trabajo más pesado: 32 imágenes de 400x400

| Workers | Secuencial | Paralelo | Speedup | Eficiencia |
|---|---|---|---|---|
| 1 | 3.10 s | 3.10 s | 1.00x | 100% |
| 2 | 3.05 s | 1.70 s | 1.80x | 90% |
| 4 | 2.98 s | 0.98 s | 3.04x | 76% |
| 8 | 2.94 s | 0.69 s | 4.29x | 54% |
| 16 | 4.78 s* | 1.24 s | 3.84x | 24% |

\* Las mediciones en WSL tienen bastante ruido: en otra ronda, con 16 workers dio
0.56 s y 5.47x. Los valores de 1 a 8 workers se repitieron de forma estable.

Observaciones:

- El speedup crece, pero **nunca llega a ser lineal**. Cada worker suma costo de
  arranque, las imágenes se mandan serializadas y la parte secuencial (crear
  las imágenes y juntar los resultados) no se paraleliza (ley de Amdahl).
- Con 1 worker el Pool no gana nada: es el mismo trabajo más el overhead.
- Pasados los 8 workers, la eficiencia se desploma. Tener más procesos que
  núcleos físicos no ayuda con trabajo CPU-bound, y esta máquina tiene 16 CPUs
  lógicas (con hyperthreading) compartidas con Windows.
- Con threads, esto no escalaría: el blur es Python puro y el GIL lo serializa.
  Por eso para trabajo CPU-bound se usan procesos.

## Checklist de la consigna

- [x] Múltiples imágenes aleatorias
- [x] Filtro aplicado a cada una
- [x] `Pool.map` para el paralelo
- [x] Tiempo secuencial vs paralelo
- [x] Speedup
- [x] `if __name__ == "__main__":` (necesario con `spawn`: el hijo reimporta el módulo)
