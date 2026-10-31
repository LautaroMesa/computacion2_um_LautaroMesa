# Clase 22 — concurrent.futures

Ejercicio obligatorio 2: `map` contra `as_completed`.

## Archivos

| Archivo | Qué es |
|---|---|
| `patrones.py` | El de la cátedra: `map`, `as_completed`, el truco del dict y `wait` |
| `mis_patrones.py` | Lo mío: `calculada` (pregunta 2), `urls` (patrón del dict con 5 URLs reales, pregunta 10), `hashable` (pregunta 11), `wait` (`FIRST_COMPLETED` / `FIRST_EXCEPTION` / `ALL_COMPLETED`) y `primero` (pregunta 14) |

## Cómo correr

```bash
docker build -t clase22 .
docker run --rm clase22                                  # patrones.py
docker run --rm clase22 python mis_patrones.py calculada # también: urls, hashable, wait, primero
```

Solo usa la biblioteca estándar. Corrió en Ubuntu 24.04 (WSL2), Python 3.12.

---

## Parte A: medir

**1. Los tiempos de las dos primeras secciones** (`patrones.py`):

```
1. map(): resultados EN ORDEN DE ENTRADA
  lenta    disponible a los 0.50s
  rapida   disponible a los 0.50s
  media    disponible a los 0.50s
  otra     disponible a los 0.50s

2. as_completed(): resultados A MEDIDA QUE TERMINAN
  rapida   disponible a los 0.10s
  media    disponible a los 0.20s
  otra     disponible a los 0.40s
  lenta    disponible a los 0.50s
```

**2. Con `map`, ¿cuándo estuvo disponible `rapida` y cuándo se calculó?** Para
verlo, en `mis_patrones.py calculada` cada tarea devuelve también el momento en
que terminó (medido en el thread del pool):

```
map(): cuándo se CALCULÓ cada una y cuándo me la ENTREGÓ map

  lenta   calculada a los 0.50s, entregada a los 0.50s (esperó 0.00s)
  rapida  calculada a los 0.10s, entregada a los 0.50s (esperó 0.40s)
  media   calculada a los 0.20s, entregada a los 0.50s (esperó 0.30s)
  otra    calculada a los 0.40s, entregada a los 0.50s (esperó 0.10s)

as_completed(): lo mismo

  rapida  calculada a los 0.10s, entregada a los 0.10s (esperó 0.00s)
  media   calculada a los 0.20s, entregada a los 0.20s (esperó 0.00s)
  otra    calculada a los 0.40s, entregada a los 0.40s (esperó 0.00s)
  lenta   calculada a los 0.50s, entregada a los 0.50s (esperó 0.00s)
```

`rapida` estuvo **calculada a los 0,10 s** pero `map` me la **entregó a los
0,50 s**: estuvo 0,40 s lista, guardada en su Future, esperando a que `lenta`
(que va primera en la lista) terminara.

**3. ¿Por qué el total es el mismo?** Porque en los dos casos las 4 tareas se
mandan al pool **de entrada** (`map` también hace `submit` de todas antes de
devolver el iterador) y corren al mismo tiempo en 4 threads. El total es lo
que tarda la más lenta: 0,5 s. Lo que cambia no es **cuándo se calculan** sino
**en qué orden me las da** el iterador: `map` recorre los futures en el orden
de la entrada y se bloquea en el primero que no terminó; `as_completed` me da
el que termine primero.

**4. En una frase:** `map` garantiza que **el i-ésimo resultado corresponde a
la i-ésima entrada** (el orden); `as_completed` no garantiza ningún orden, solo
que cada resultado llega apenas está listo.

## Parte B: cuándo cada uno

**5. 1000 URLs → lista de códigos en el mismo orden: `map`.** Lo que se pide es
justamente el orden de entrada: el resultado `i` tiene que ser el de la URL `i`.
Con `as_completed` tendría que reordenar a mano. Y no gano nada recibiendo antes
los primeros, porque igual necesito la lista completa.

**6. Barra de progreso con 1000 archivos: `as_completed`.** La barra tiene que
avanzar cada vez que **termina** un archivo, cualquiera. Con `map`, si el primer
archivo es el más pesado, la barra se queda en 0 % hasta que termina y después
salta de golpe, aunque otros 900 ya estén listos.

**7. 50 imágenes, guardarlas apenas lleguen: `as_completed`.** "Apenas lleguen"
es literalmente lo que hace. Además libera memoria: cada imagen se escribe y se
descarta en lugar de quedar retenida esperando a una lenta de adelante.

**8. Promedio de un cálculo sobre 100 números: cualquiera, pero `map` es lo más
simple** (`statistics.mean(pool.map(f, numeros))`). La suma no depende del
orden, así que `as_completed` no aporta nada, y no hay nada que hacer con los
resultados parciales. Si el cálculo es CPU-bound, el pool tiene que ser de
**procesos** (clase 21), y ahí conviene `map(..., chunksize=...)` para no pagar
un viaje de pickle por número.

## Parte C: la correspondencia

**9. Con `as_completed`, ¿cómo sé de qué entrada era cada resultado?** El Future
no dice qué argumentos recibió. La forma es armar un **dict `{future: dato
original}`** al hacer los `submit` y, cuando `as_completed` me da un future,
buscarlo en el dict. (La otra forma es que la función devuelva también su
entrada, como hace `tarea()` en `patrones.py`, pero eso no sirve si la función
**falla**: la excepción no trae la entrada).

**10. El patrón del dict con 5 URLs reales, reportando cuál falló:**

```python
with ThreadPoolExecutor(5) as pool:
    futuros = {pool.submit(estado_http, u): u for u in URLS}
    for f in as_completed(futuros):
        url = futuros[f]                         # de qué entrada era
        try:
            codigo = f.result()
            print(f'{codigo}  {url}')
        except Exception as e:
            print(f'FALLÓ {url}: {type(e).__name__}: {e}')
```

```
5 URLs con as_completed y el dict {future: url}

   0.12s  FALLÓ https://esto-no-existe.invalid/: URLError: <urlopen error [Errno -2] Name or service not known>
   0.21s  200  https://example.com/
   0.32s  200  https://www.python.org/
   0.54s  404  https://httpbin.org/status/404
   1.54s  200  https://httpbin.org/delay/1
```

La que falló (el dominio no existe, falla el DNS) llegó **primera**, y sin el
dict no sabría cuál era: la excepción no trae la URL. El 404 no lo cuento como
falla: el servidor respondió, es una respuesta HTTP válida (lo mismo que hice
en la clase 20 y en el TP2, donde un 4xx de `descargar` es un resultado y no un
error).

**11. ¿Por qué un `Future` puede ser clave de un dict?**

```
  hash(a) = 8701550256853   id(a) = 139224804109648   id(a) // 16 = 8701550256853
  type(a).__hash__ is object.__hash__ -> True
  type(a).__eq__   is object.__eq__   -> True
  a == b -> False  (mismos argumentos, mismo resultado, distinto Future)
```

Para ser clave, un objeto tiene que ser **hashable**: tener un `__hash__` que
no cambie mientras vive y un `__eq__` coherente con él (si `a == b` entonces
`hash(a) == hash(b)`). `Future` no redefine ninguno de los dos: hereda los de
`object`, que usan la **identidad**. El hash sale de `id()` (en CPython,
`id // 16`, como se ve arriba) y `==` es `is`. Que el estado del Future cambie
(de PENDING a FINISHED) no importa, porque ni el hash ni la igualdad miran el
estado. Y la identidad es justo lo que necesito: dos futures con los mismos
argumentos son **dos trabajos distintos** (`a == b` da `False`).

## Parte D: wait

**12. ¿Qué devuelve `wait()`?** Una tupla con **dos conjuntos** de futures:
`(listos, pendientes)` (es un `namedtuple` `DoneAndNotDoneFutures(done,
not_done)`). No devuelve resultados: hay que pedirle `.result()` a cada uno. En
`patrones.py` con `FIRST_COMPLETED` volvió a los 0,10 s con 1 listo y 3
pendientes.

**13. `FIRST_EXCEPTION`.** Con tres tareas: `lenta` (0,6 s), `rota` (falla a
los 0,2 s) y `rapida` (0,1 s):

```
FIRST_COMPLETED  volvió a los 0.10s  listos=['rapida']  pendientes=['lenta', 'rota']
FIRST_EXCEPTION  volvió a los 0.20s  listos=['rapida', 'rota']  pendientes=['lenta']
ALL_COMPLETED    volvió a los 0.60s  listos=['lenta', 'rapida', 'rota']  pendientes=[]
```

Vuelve **cuando la primera tarea lanza una excepción** (0,20 s), no cuando
termina la primera (`rapida`, a los 0,10 s, no la hizo volver). Si ninguna
falla, se comporta como `ALL_COMPLETED`: espera a todas. Sirve para "corré
todo, pero si algo falla quiero enterarme ya y abortar el resto".

**14. Tres servidores, me quedo con la primera respuesta:**

```python
pool = ThreadPoolExecutor(3)
futuros = {pool.submit(consultar, s, d): s for s, d in servidores}
listos, pendientes = wait(futuros, return_when=FIRST_COMPLETED)
ganador = listos.pop()
for f in pendientes:
    f.cancel()
pool.shutdown(wait=False, cancel_futures=True)
```

```
  a los 0.30s ganó espejo-br: 'respuesta de espejo-br'
  cancel() de espejo-us: False  (ya estaba corriendo: True)
  cancel() de espejo-ar: False  (ya estaba corriendo: True)
  sigo trabajando a los 0.30s, los perdedores terminan solos de fondo
```

**¿Qué hago con los otros dos?** Les pido `cancel()`, pero **devuelve
`False`**: ya estaban corriendo, y un thread que ya está ejecutando código **no
se puede interrumpir** desde afuera (`cancel()` solo saca de la cola a los que
todavía no arrancaron). Lo que sí puedo hacer es **no esperarlos**:
`shutdown(wait=False)` me deja seguir a los 0,30 s y los perdedores terminan
de fondo, y su resultado se descarta. Ojo con un detalle: si usara `with
ThreadPoolExecutor(...)`, el `__exit__` hace `shutdown(wait=True)` y me quedaría
esperando al más lento (1,5 s), y perdería toda la ventaja. Si de verdad hay
que cortarlos (para no gastar conexiones), la función tiene que colaborar: un
timeout en el request o un `threading.Event` que revise. Es la diferencia con
`task.cancel()` de asyncio (clase 21), que sí interrumpe una corrutina en curso
porque le inyecta `CancelledError` en su próximo `await`.

---

## Verificación

- [x] Los tiempos de las dos formas, con números propios (preguntas 1 y 2)
- [x] Por qué el total es igual pero la entrega distinta (pregunta 3)
- [x] Qué garantiza `map` que `as_completed` no (pregunta 4)
- [x] Los cuatro casos de la parte B elegidos y justificados
- [x] El patrón del diccionario implementado (pregunta 10)
- [x] Por qué un Future puede ser clave de un dict (pregunta 11)
- [x] `wait` con `FIRST_COMPLETED` y `FIRST_EXCEPTION` (preguntas 12-14)
