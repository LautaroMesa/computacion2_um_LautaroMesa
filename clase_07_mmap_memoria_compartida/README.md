# Clase 7 — mmap y memoria compartida

Ejercicio obligatorio 5: `Value` y `Array` compartidos.

## Archivos

| Archivo | Qué hace |
|---|---|
| `race_value.py` | 5.1: 4 procesos incrementan un `Value('i')` sin lock y después con `get_lock()` |
| `cuadrados_array.py` | 5.2: `Array('i', 1000)` repartido entre 4 procesos, verifica `i*i` |
| `senos_array.py` | Tarea: `Array('d', 100)` con `sin(i*0.01)`; bonus con `Value('d')` acumulando la suma, sin y con lock |

## Cómo correr

```bash
docker build -t clase7 .
docker run --rm clase7 python race_value.py
docker run --rm clase7 python cuadrados_array.py
docker run --rm clase7 python senos_array.py            # 100 elementos
docker run --rm clase7 python senos_array.py 400000     # para forzar la race
```

## Resultados (Linux, 4 procesos)

### 5.1 — Contador

```
--- Sin lock ---
Esperado: 400000
Obtenido: 147812
Diferencia: 252188 (incrementos perdidos)
Tiempo: 0.37s

--- Con get_lock() ---
Esperado: 400000
Obtenido: 400000
Diferencia: 0
Tiempo: 0.89s
```

Se perdió más de la mitad de los incrementos. El número cambia en cada corrida.

**¿Por qué falla si `Value` ya trae un lock?** El lock de `Value` protege cada
*acceso* por separado, no la operación completa. `contador.value += 1` son dos
accesos: un `get` (con lock) y un `set` (con lock), y entre medio otro proceso
puede leer el mismo valor viejo. Para que el `+=` sea atómico hay que tomar el
lock alrededor de las dos operaciones: `with contador.get_lock():`.

El lock tiene su costo: tarda unas 2,4 veces más, porque cada incremento
adquiere y libera un semáforo.

### 5.2 — Cuadrados

```
Calculo completado en 0.0070s
resultado[0] = 0
resultado[10] = 100
resultado[99] = 9801
resultado[999] = 998001
Errores: 0
```

Acá no hay race: cada proceso escribe en **su** rango de índices y ninguno se
pisa con otro. Por eso uso `Array(..., lock=False)`, porque el lock no protegería nada.

### Tarea — Senos con suma compartida

Con 100 elementos:

```
Primeros 20 resultados (de 100):
  sin(0.00) = 0.000000
  sin(0.01) = 0.010000
  ...
Errores en el Array: 0

Suma esperada:     45.548651
Suma sin lock:     45.548651  (diferencia +0.000000)
Suma con get_lock: 45.548651  (diferencia +0.000000)
```

Con 100 elementos **la race no aparece**, pero no porque el código esté bien:
cada proceso hace 25 sumas y termina antes de que el siguiente llegue a
arrancar, así que nunca se solapan. Con 400.000 elementos sí se ve:

```
Suma esperada:     173.335006
Suma sin lock:     982.840749  (diferencia -809.505742)
Suma con get_lock: 173.335006  (diferencia +0.000000)
```

La suma sin lock da **de más**. Pasado `i*0.01 > π` los senos son negativos,
así que perder sumas negativas hace crecer el total. Una race no solo "pierde"
valor: deja un resultado que puede quedar por arriba o por abajo del correcto,
según qué escrituras se pierdan.

Una alternativa mejor que el lock por elemento: que cada proceso acumule en una
variable local y haga **un solo** `+=` con lock al final. Así se toma el lock
4 veces en total en lugar de 400.000.

## Checklist de la consigna

- [x] `Value` compartido con race condition demostrada
- [x] `Array` compartido con el trabajo dividido entre procesos
- [x] Verificación de resultados con reporte de errores
- [x] Diferencia entre el valor esperado y el obtenido
