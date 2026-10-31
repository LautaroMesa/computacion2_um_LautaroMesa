# Clase 23 — Celery I

Ejercicio obligatorio 1: el salto de escala.

## Archivos

| Archivo | Qué es |
|---|---|
| `tareas.py` | El de la cátedra (la app de Celery y sus 4 tareas). Único cambio: la URL del broker sale de `REDIS_URL` si está definida, para poder correr el worker dentro de un contenedor |
| `encolar.py`, `consultar.py` | Los de la cátedra: encolar y morirse, consultar por id desde otro proceso |
| `decodificar.py` | Lo mío (parte B): lee el primer mensaje de la cola sin sacarlo, decodifica el `body` de base64 y muestra qué viaja |
| `docker-compose.yml` | El de la cátedra: Redis 7 en el puerto 6399 del host |
| `Dockerfile` | Lo mío: imagen con Celery para correr el worker y los scripts dentro de Docker |

## Cómo correr

Como en la clase (anexo de la cátedra), con un entorno virtual:

```bash
docker compose up -d                                   # Terminal 1: el broker
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
celery -A tareas worker --loglevel=info --concurrency=2 # Terminal 2: el worker
python3 encolar.py && python3 consultar.py             # Terminal 3: vos
```

Con Docker, sin instalar nada: el worker y los scripts en contenedores sobre la
red de compose (ahí el broker es `redis:6379`, no `localhost:6399`):

```bash
docker compose up -d
docker build -t clase23 .
docker run --rm --network clase_23_celery_1_default clase23 python encolar.py
docker run -d --name w23 --network clase_23_celery_1_default clase23   # el worker
docker run --rm --network clase_23_celery_1_default clase23 python consultar.py <id>
docker rm -f w23 && docker compose down
```

Corrió en Ubuntu 24.04 (WSL2), Python 3.12, Celery 5.6.3, Redis 7 (Docker
Desktop). Lo verifiqué de las dos formas.

---

## Parte A: los tres pasos (sin ningún worker)

```
$ python3 encolar.py
  id:     0af67d7a-dd2f-493c-abd3-7f74c0112611
  estado: PENDING
  Fijate que delay() volvio enseguida: no espero el resultado.

$ docker compose exec redis redis-cli LLEN celery
1

$ python3 consultar.py
  id:           0af67d7a-dd2f-493c-abd3-7f74c0112611
  state:        PENDING
  ready():      False
  todavia no termino (o el worker no esta corriendo)
```

**1.** Estado **`PENDING`**, y `LLEN celery` = **1**: el mensaje está en la
lista `celery` de Redis, esperando a que alguien lo saque.

**2. Si `LLEN` diera 0** es porque **había un worker corriendo** (de una prueba
anterior, en otra terminal o en un contenedor) que ya tomó el mensaje. Una vez
que el worker lo saca de la lista, `LLEN` baja a 0 aunque la tarea todavía se
esté ejecutando. Se arregla bajando ese worker (Ctrl+C, o `docker rm -f` si
estaba en un contenedor) y volviendo a encolar. A mí me dio 1 de entrada.
(Otra causa posible: que `encolar.py` apunte a otro Redis o a otra base, por
ejemplo uno local en el 6379; por eso la cátedra usa el 6399.)

**3. Arranco el worker. ¿Cuánto tarda en tomar la tarea?**

```
--- desde que lancé el worker hasta SUCCESS: 2.75 s (incluye 1 s de sleep de sumar)
  log: [16:38:55,453] Connected to redis://localhost:6399/0
  log: [16:38:56,519] celery@HPPavilion ready.
  log: [16:38:56,522] Task tareas.sumar[0af67d7a-...] received
  log: [16:38:57,532] Task tareas.sumar[0af67d7a-...] succeeded in 1.0088s: 5
```

Una vez que el worker está listo (`ready.`), la toma en **3 ms** (de 56,519 a
56,522). Casi todo el tiempo es el arranque del worker: importar Celery,
conectarse a Redis y crear los 2 procesos del pool (~1 s). Después, el `sleep`
de 1 s de `sumar`.

**4. `consultar.py` de nuevo:**

```
  id:           0af67d7a-dd2f-493c-abd3-7f74c0112611
  state:        SUCCESS
  ready():      True
  successful(): True
  result:       5
```

Y `LLEN celery` volvió a 0. El resultado lo consultó un **tercer proceso**,
que no encoló nada y no ejecutó nada: solo tenía el id.

**5. ¿Por qué es imposible con `ThreadPoolExecutor`?** Porque un `Future` es
un objeto **en la memoria del proceso** que hizo el `submit`, y la cola del
pool también. Si el proceso termina, mueren la cola, los threads y el Future,
y no hay ningún id que otro proceso pueda consultar. Con Celery la tarea y su
resultado viven en Redis, **afuera** de todos los procesos.

## Parte B: el mensaje

**6. El mensaje crudo** (`LINDEX celery 0`, con un worker apagado):

```json
{"body": "W1syLCAzXSwge30sIHsiY2FsbGJhY2tzIjogbnVsbCwgImVycmJhY2tzIjogbnVsbCwgImNoYWluIjogbnVsbCwgImNob3JkIjogbnVsbH1d",
 "content-encoding": "utf-8", "content-type": "application/json",
 "headers": {"lang": "py", "task": "tareas.sumar", "id": "fde8c362-6e8d-4713-b09a-432f84d9095a",
             "shadow": null, "eta": null, "expires": null, "group": null, "group_index": null,
             "retries": 0, "timelimit": [null, null], "root_id": "fde8c362-...", "parent_id": null,
             "argsrepr": "(2, 3)", "kwargsrepr": "{}", "origin": "gen1691@HPPavilion",
             "ignore_result": false, "replaced_task_nesting": 0, "stamped_headers": null, "stamps": {}},
 "properties": {"correlation_id": "fde8c362-...", "reply_to": "a84a430e-...", "delivery_mode": 2,
                "delivery_info": {"exchange": "", "routing_key": "celery"}, "priority": 0,
                "body_encoding": "base64", "delivery_tag": "a6e41806-..."}}
```

**7. El `body` decodificado** (`python3 decodificar.py`):

```
body decodificado: [[2, 3], {}, {"callbacks": null, "errbacks": null, "chain": null, "chord": null}]
  args=[2, 3]  kwargs={}  callbacks=None
```

Es una lista JSON de tres elementos: los **argumentos posicionales** `[2, 3]`,
los **argumentos con nombre** `{}` y opciones de encadenamiento (callbacks,
chain, chord), todas vacías. El mensaje completo pesa 944 bytes.

**8. ¿Aparece el código de la función?** **No.** En ningún lado del mensaje
está `time.sleep` ni `return a + b`. Viaja solo el **nombre** de la tarea, en el
header `"task": "tareas.sumar"`.

**9. ¿Cómo sabe el worker qué ejecutar?** Al arrancar, el worker **importa**
`tareas.py` (eso es el `-A tareas`), y cada `@app.task` registra la función en
un diccionario de la app: `app.tasks['tareas.sumar'] = sumar`. Cuando llega un
mensaje, busca el header `task` en ese diccionario y llama a la función con
`args` y `kwargs`. Es la misma idea que `pickle` con funciones (clase 21): se
manda el nombre importable, no el código. Por eso **el que encola y el worker
tienen que tener el mismo código**.

**10. ¿Qué pasa si el worker no tiene el `tareas.py`?** Lo probé de dos
maneras:

Desde otro directorio, sin ningún `tareas.py`: el worker **ni arranca**.

```
Error:
Unable to load celery application.
The module tareas was not found.
```

Más interesante: con un `tareas.py` que crea la misma app (mismo broker) pero
**no define `sumar`**. El worker arranca, toma el mensaje y:

```
[ERROR/MainProcess] Received unregistered task of type 'tareas.sumar'.
The message has been ignored and discarded.

Did you remember to import the module containing this task?
...
KeyError: 'tareas.sumar'
```

El mensaje **se pierde**: `LLEN celery` quedó en 0, y la tarea queda en
`FAILURE` en el backend con `Task of kind 'tareas.sumar' never registered`.
Es el `KeyError` del diccionario de la pregunta 9. En producción esto pasa al
desplegar el que encola con una tarea nueva antes que los workers.

## Parte C: el id como recibo

**11 y 12. Bajar todo y volver a levantar.** Antes de bajar, el resultado
estaba en Redis como una clave con vencimiento:

```
$ redis-cli KEYS 'celery-task-meta-*'
celery-task-meta-fde8c362-6e8d-4713-b09a-432f84d9095a
celery-task-meta-0af67d7a-dd2f-493c-abd3-7f74c0112611
$ redis-cli TTL celery-task-meta-0af67d7a-dd2f-493c-abd3-7f74c0112611
86386
```

Después de `docker compose down` y `docker compose up -d`:

```
  id:           0af67d7a-dd2f-493c-abd3-7f74c0112611
  state:        PENDING
  ready():      False
$ redis-cli DBSIZE
0
```

**El resultado no sobrevivió.** El resultado vivía en el **backend**, que es
el mismo Redis, en la clave `celery-task-meta-<id>`. `docker compose down`
**borra el contenedor**, y con él la memoria de Redis. El compose no monta
ningún volumen con nombre para `/data`, así que el contenedor nuevo arranca
con un Redis vacío (`DBSIZE` 0). Sobrevivió a que **mueran los procesos de
Python** (el que encoló y el worker), pero no a que muera el **broker/backend**.
Para que sobreviva haría falta persistencia en Redis (un volumen para `/data`
más RDB o AOF) o un backend en una base de datos. Además, aunque Redis no se
caiga, el resultado **vence**: el TTL de 86386 s es el `result_expires` por
defecto de Celery (1 día).

**13. Un id inventado:**

```
  id inventado -> state: 'PENDING'
                  ready(): False
                  result: None
```

Devuelve **`PENDING`**, igual que la tarea en cola de la parte A, e igual que
el id real después de bajar Redis en la pregunta 11. `PENDING` no significa "en
la cola": significa **"el backend no tiene nada sobre este id"**. Celery no
valida que el id exista, porque recién escribe en el backend cuando la tarea
termina.

**14. ¿Cómo distinguiría "está en la cola" de "no existe"?** El backend no
sirve para eso, así que hay que guardar el dato del lado de uno:

- **Registrar el id al encolar**: guardar los ids que encolé (en una base, en
  Redis, o como hace `encolar.py` en un archivo). Si el id no está en mi
  registro, no existe. Si está y el backend dice `PENDING`, está en la cola.
- **`task_track_started=True`**: el worker escribe `STARTED` al tomarla, lo que
  distingue "en cola" de "ejecutándose" (pero no "en cola" de "inexistente").
- **Mirar la cola**: buscar el id en `LRANGE celery 0 -1`. Funciona, pero es
  O(n) y no ve las tareas que el worker ya tomó y no terminó.

Lo correcto es lo primero. Es lo mismo que hice en el TP2: el registro de
tareas es mío y un id desconocido da 404, no un estado inventado.

---

## Verificación

- [x] Los tres pasos corriendo, con `LLEN celery` en 1 sin workers
- [x] El estado y el resultado de la tarea huérfana, consultados desde un tercer proceso
- [x] Por qué es imposible con `ThreadPoolExecutor` (pregunta 5)
- [x] El mensaje decodificado: qué viaja y qué no (preguntas 6-9)
- [x] Qué pasa cuando el worker no tiene el código de la tarea (pregunta 10)
- [x] Qué pasa con el resultado al bajar y levantar todo (preguntas 11-12): **no
      sobrevive**, porque Redis sin volumen pierde los datos
- [x] La trampa de `PENDING` con un id inventado (preguntas 13-14)
