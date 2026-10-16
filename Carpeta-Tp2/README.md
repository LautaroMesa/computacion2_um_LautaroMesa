# TP2 — Plataforma de tareas distribuidas

Computación II — Universidad de Mendoza — 2026
Alumno: Lautaro Mesa (legajo 64060)

Un servicio HTTP al que se le encargan trabajos (`descargar`, `hashear`,
`esperar`), que los ejecuta de forma concurrente en un pool de workers
asíncronos y permite consultar su estado y resultado, cancelarlos y seguir sus
cambios en vivo. Todo corre en **un solo event loop** (el de uvicorn); lo único
que sale de ahí es el cálculo de `hashear`, que va a un `ProcessPoolExecutor`.

---

## 1. Cómo correrlo

```bash
docker compose up --build
```

Levanta dos servicios:

| Servicio | Puerto | Qué es |
|---|---|---|
| `api` | `8000` | La plataforma. Documentación interactiva en http://127.0.0.1:8000/docs |
| `lento` | `8081` | Un servidor HTTP que responde con una demora fija (`GET /demora/<segundos>`), para medir `descargar` sin depender de internet |

Al apagar (`Ctrl+C` o `docker compose stop`) el estado se vuelca a
`./estado/estado_<timestamp>.json`.

> Usar `127.0.0.1` y no `localhost`. En Windows, `localhost` intenta primero
> IPv6 y cada conexión tarda 0,2 s de más. Lo medí: el servidor responde en 2 ms,
> pero `curl localhost` tardaba 205 ms en conectarse.
> En PowerShell, `curl` es un alias de `Invoke-WebRequest`: usar `curl.exe`.

### Configuración (variables de entorno)

Se pueden cambiar sin editar nada: `TP2_WORKERS=8 docker compose up --build`.

| Variable | Defecto | Qué controla |
|---|---|---|
| `TP2_WORKERS` | 4 | Corrutinas que consumen la cola |
| `TP2_PROCESOS` | 2 | Procesos del `ProcessPoolExecutor` (para `hashear`) |
| `TP2_MAX_COLA` | 1000 | Capacidad de la `asyncio.Queue`; con la cola llena, el POST da 503 |
| `TP2_TIMEOUT` | 60 | Timeout por defecto de cada tarea (segundos) |
| `TP2_GRACIA` | 10 | Al apagar, cuánto se espera a las tareas en curso |
| `TP2_HASH_EXECUTOR` | `proceso` | Dónde corre `hashear`: `proceso`, `thread` o `ninguno` (dentro del loop, **solo para la medición 2**) |

### Ejemplos con curl

```bash
# Encolar una tarea de cada tipo (el POST responde 202 en el acto)
curl -X POST http://127.0.0.1:8000/tareas -H 'Content-Type: application/json' \
     -d '{"tipo": "esperar", "parametros": {"segundos": 30}}'

curl -X POST http://127.0.0.1:8000/tareas -H 'Content-Type: application/json' \
     -d '{"tipo": "descargar", "parametros": {"urls": ["https://example.com", "https://www.python.org"]}}'

curl -X POST http://127.0.0.1:8000/tareas -H 'Content-Type: application/json' \
     -d '{"tipo": "hashear", "parametros": {"texto": "hola", "iteraciones": 5000000}, "timeout": 120}'

# Consultar
curl http://127.0.0.1:8000/tareas                       # todas (las últimas 100)
curl "http://127.0.0.1:8000/tareas?estado=ejecutando"   # filtradas por estado
curl http://127.0.0.1:8000/tareas/1                     # estado, progreso y resultado
curl http://127.0.0.1:8000/estadisticas
curl http://127.0.0.1:8000/metrics                      # formato Prometheus

# Cancelar (en cola o en ejecución); devuelve el estado final
curl -X DELETE http://127.0.0.1:8000/tareas/1

# Seguir los cambios de estado en vivo (WebSocket; requiere `pip install websockets`)
python -m websockets ws://127.0.0.1:8000/eventos
```

Respuesta de un POST:

```json
{"id": 1, "tipo": "esperar", "estado": "pendiente", "parametros": {"segundos": 30.0},
 "timeout": 60.0, "creada": "2026-10-16T22:18:51.499295Z", "iniciada": null,
 "terminada": null, "duracion": null, "progreso": null, "worker": null,
 "resultado": null, "error": null}
```

### API

| Método | Ruta | Qué hace | Códigos |
|---|---|---|---|
| `POST` | `/tareas` | Encola una tarea; devuelve su `id` y estado inicial | 202, 422, 503 |
| `GET` | `/tareas?estado=&limite=` | Lista las tareas, con filtro opcional por estado | 200, 422 |
| `GET` | `/tareas/{id}` | Estado, progreso y resultado | 200, 404 |
| `DELETE` | `/tareas/{id}` | Cancela una tarea en cola o en ejecución | 200, 404, 409 |
| `GET` | `/estadisticas` | Totales por estado, tiempos promedio, workers ocupados, cola | 200 |
| `GET` | `/metrics` | Lo mismo en formato Prometheus (bonus) | 200 |
| `WS` | `/eventos` | Cada cambio de estado, en tiempo real (bonus) | — |

Estados: `pendiente` → `ejecutando` → `completada` / `fallida` / `cancelada`
(y `pendiente` → `cancelada` si se cancela antes de arrancar). Cualquier otra
transición se rechaza: es un bug.

| Tipo | Parámetros | Resultado |
|---|---|---|
| `descargar` | `urls` (1 a 100, http/https), `secuencial` (opcional, para comparar) | Por URL: código HTTP, bytes y tiempo, o el error; además `tiempo_total`, `suma_de_tiempos`, `ok` y `errores` |
| `hashear` | `texto`, `iteraciones` (hasta 10⁸) | SHA-256 aplicado `iteraciones` veces, y el tiempo de cálculo |
| `esperar` | `segundos` (hasta 3600) | Cuánto durmió |

Todas aceptan `timeout` (segundos). Si se vence, la tarea pasa a `fallida` con
el motivo `timeout: supero los Ns`. El timeout cuenta **desde que la tarea
arranca**, no el tiempo que pasa en la cola.

### Tests

```bash
pip install -r requirements-dev.txt
pytest                 # 28 tests, ~40 s
```

---

## 2. Arquitectura

```
                         un solo proceso, un solo event loop (uvicorn)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                                                                              │
 │  Cliente ──HTTP──▶ FastAPI ──▶ Registro (dict id → Tarea)                    │
 │    ▲               POST /tareas      │   estados, tiempos, resultado         │
 │    │                 │  1. verificar lugar en la cola                        │
 │    │                 │  2. registrar la tarea (pendiente)                    │
 │    │                 │  3. put_nowait(id) ──▶ asyncio.Queue(maxsize=1000)    │
 │    │                 │  4. responder 202          │                          │
 │    │                 ▼                            │ await get()              │
 │    │            202 + id                          ▼                          │
 │    │                                   ┌──────────────────────┐              │
 │    │   GET /tareas/{id} ◀── estado ─── │ worker-0 … worker-N  │              │
 │    │                                   │  (corrutinas)        │              │
 │    │   DELETE ──▶ job.cancel() ──────▶ │  cada tarea corre en │              │
 │    │                                   │  su propio Task (job)│              │
 │    │   WS /eventos ◀── cambios ──────  └───┬──────────┬───────┘              │
 │    │                                       │          │                      │
 │    │                     esperar ──────────┘          │                      │
 │    │                     asyncio.sleep                │                      │
 │    │                                                  │                      │
 │    │                     descargar ── TaskGroup ── httpx.AsyncClient ──────────── Internet
 │    │                                  (una task hija   (pool keep-alive)     │    / lento:8081
 │    │                                   por URL)                              │
 │    │                     hashear ── run_in_executor, por bloques ─┐          │
 │    │                                                              │          │
 └────┼──────────────────────────────────────────────────────────────┼──────────┘
      │                                                              ▼
      │                                          ProcessPoolExecutor (spawn)
      │                                          proceso 1 … proceso P
      │                                          sha256_iterado(bytes, n) -> bytes
      │
      └── SIGTERM/SIGINT ──▶ dejar de aceptar ─▶ esperar (gracia) ─▶ cancelar ─▶ estado_<ts>.json
```

### Flujo de una tarea

1. **`POST /tareas`**. FastAPI valida el cuerpo con Pydantic: es una *unión
   discriminada* por `tipo`, y cada tipo tiene su modelo de `parametros`. Si algo
   no cumple, responde **422 sin llegar a la cola**.
2. Se verifica que haya lugar (`cola.full()`) y que el servidor no se esté
   apagando. Si no, **503** con `Retry-After`.
3. Se registra la tarea como `pendiente`, se pone su id en la cola con
   `put_nowait` y se responde **202**. El POST no espera nada: tarda ~0,1 ms dentro
   de la app.
4. Un worker libre saca el id (`await cola.get()`). Si la tarea fue cancelada
   mientras estaba en la cola, la saltea.
5. La marca `ejecutando` y crea un **`asyncio.Task` propio para la tarea** (el
   *job*), envuelto en `asyncio.timeout(tarea.timeout)`. El worker espera al job.
6. Según el tipo, el job duerme (`esperar`), lanza las descargas en un
   `TaskGroup` (`descargar`) o manda bloques de hash al pool de procesos
   (`hashear`), y va actualizando `progreso`.
7. Cuando el job termina, el worker anota el resultado: `completada`; `fallida`
   si hubo una excepción o venció el timeout; `cancelada` si lo cancelaron. Y
   vuelve a la cola.
8. Cada cambio de estado se publica en las colas de los suscriptores de `/eventos`.

### Archivos

```
app/
  main.py          FastAPI: endpoints, lifespan (arranque y apagado), señales
  pool.py          asyncio.Queue + workers; ejecución, timeout y cancelación de cada tarea
  tareas.py        las tres tareas; httpx.AsyncClient y ProcessPoolExecutor compartidos
  cpu.py           sha256_iterado: la única función que corre en otro proceso
  registro.py      tareas en memoria, transiciones de estado, eventos
  persistencia.py  volcado a estado_<timestamp>.json y lectura al arrancar
  modelos.py       modelos Pydantic de pedidos y respuestas
  config.py        configuración por variables de entorno
scripts/
  medir_concurrencia.py  medición 1
  medir_bloqueo.py       medición 2
  medir_techo.py         medición 3
  servidor_lento.py      servidor HTTP con demora (asyncio.start_server)
  cliente_crudo.py       cliente HTTP mínimo con asyncio (para la medición 3)
tests/             28 tests con pytest-asyncio
```

---

## 3. Decisiones de diseño

### ¿Por qué `asyncio.Queue` y no `queue.Queue`?

Porque los productores (el endpoint POST) y los consumidores (los workers) son
**corrutinas en el mismo hilo**. `queue.Queue.get()` es bloqueante: un worker
esperando trabajo **bloquearía el hilo entero**, es decir, el event loop, y con
él la API, los otros workers y todo lo demás. `queue.Queue` está hecha para
coordinar *threads*, y por eso usa un lock y variables de condición del sistema
operativo.

`asyncio.Queue.get()`, en cambio, es una corrutina: si la cola está vacía, el
worker se **suspende** con `await` y le devuelve el control al loop, que sigue
atendiendo pedidos. Cuando el POST hace `put_nowait`, el loop despierta a uno de
los workers suspendidos. No hay locks porque no hace falta: todo ocurre en un
solo hilo.

La cola tiene **`maxsize=1000`**. Esto es control de flujo (clase 21): si llegan
más tareas de las que se pueden absorber, el POST rechaza con 503 en vez de
acumular memoria sin límite. Uso `put_nowait` y no `await put()` porque el POST
tiene que responder en el acto: con la cola llena es mejor decirle al cliente
"reintentá más tarde" que dejarlo colgado esperando lugar.

### ¿Cómo evito que una tarea CPU-bound congele la API?

El hash corre en un **`ProcessPoolExecutor`**, a través de
`loop.run_in_executor()`. El worker hace `await` sobre el futuro y, mientras el
proceso hijo calcula, el event loop queda libre. La medición 2 lo muestra: sin
executor, un GET tardó **3.007 ms**; con procesos, **10 ms**, igual que en reposo.

¿Por qué procesos y no `asyncio.to_thread`? Por el **GIL** (clase 10). Un thread
saca el cálculo del hilo del loop, pero el cálculo sigue necesitando el GIL para
ejecutar bytecode, y se lo disputa al loop. Medido: con threads, los GET
**durante** un hash suben a 30 ms de mediana y 60 ms de máximo. Además, varios
hashes en threads no corren en paralelo: 4 a la vez tardan **7,1 s con threads y
1,9 s con procesos**.

Tres detalles:

- **El pool se crea una sola vez**, en el `lifespan`, y se precalienta (arranca
  los procesos al levantar el servidor y no en la primera tarea). Crear procesos
  es caro: con `spawn`, el pool de 2 procesos tarda ~0,4 s en estar listo (se ve
  en el log del arranque).
- **Uso `spawn` en todas las plataformas.** El comportamiento es el mismo en
  Linux, macOS y Windows, y se evita hacer `fork()` de un proceso que ya tiene
  threads, lo que en Python 3.12 da `DeprecationWarning` y puede dejar locks
  tomados en el hijo. Por eso `main.py` tiene la guarda `if __name__ ==
  '__main__'`: con `spawn`, cada proceso hijo re-importa el módulo principal.
- **Lo que viaja al proceso es mínimo**: `(bytes, int)` de ida y `bytes` de
  vuelta. La función (`cpu.py`) no importa nada de la app.

### ¿Cómo implementé la cancelación, y qué pasa con los recursos a medio usar?

**Cada tarea corre en su propio `asyncio.Task` (el job), separado del worker.**
`DELETE /tareas/{id}` hace `job.cancel()`. asyncio inyecta un `CancelledError` en
el `await` donde esté parado el job, la excepción sube por la pila corriendo
todos los `finally` y los `async with`, y el worker, que estaba en `await job`, la
recibe, anota `cancelada` y vuelve a la cola. **El worker no muere.** Si la
tarea todavía estaba en la cola, alcanza con marcarla `cancelada`: el worker que
la saque la saltea.

Para distinguir "cancelaron la tarea" de "cancelaron al worker" (en el apagado)
uso `asyncio.current_task().cancelling()` (Python 3.11). Si el cancelado es el
worker, también cancela el job, espera a que termine de limpiar y propaga la
cancelación.

Qué pasa con los recursos en cada tipo:

| Tipo | Dónde está parado al cancelar | Qué se libera |
|---|---|---|
| `esperar` | `asyncio.sleep` | Nada que liberar |
| `descargar` | leyendo la respuesta de alguna URL | Las descargas son tasks hijas de un **`asyncio.TaskGroup`**. Al cancelar la tarea, el grupo **cancela a todas las hijas y espera a que terminen** antes de propagar. Cada una está dentro de `async with cliente.stream(...)`, que al salir cierra esa conexión (no la devuelve al pool a medio leer). Un test verifica que, después del DELETE, quedan **0 tasks** de esa tarea y **0 conexiones** abiertas en el cliente |
| `hashear` | `await run_in_executor(...)` | Acá está el límite real: **un proceso que ya está calculando no se puede interrumpir** desde asyncio. Cancelar el `await` solo descarta el resultado y el proceso sigue gastando CPU. Por eso el hash se manda **por bloques de 250.000 iteraciones** (~0,18 s cada uno): la cancelación (y el timeout) cortan en el borde del bloque siguiente, y se desperdicia como mucho uno. Un test cancela un hash de 10⁸ iteraciones con un pool de 1 proceso y verifica que la siguiente tarea arranca enseguida |

Usé `TaskGroup` y no `gather` por lo que vimos en la clase 21: si una de las
hermanas falla o el padre se cancela, con `gather` las demás quedan **huérfanas**
corriendo; con `TaskGroup` se cancelan y se las espera.

El **timeout** usa el mismo mecanismo: `asyncio.timeout()` cancela lo que tiene
adentro y convierte esa cancelación en `TimeoutError`, que el worker anota como
`fallida` con el motivo.

### ¿Qué pasa si un worker lanza una excepción no capturada?

Hay dos niveles:

1. **Una excepción dentro de una tarea** (una URL rara, un bug en un ejecutor)
   no llega al worker como "no capturada". `_ejecutar` atrapa cualquier
   `Exception` del job y marca la tarea como `fallida`, con `Tipo: mensaje` en
   `error` y un warning en el log. El worker sigue. `CancelledError` no hereda de
   `Exception`, así que no se confunde con un error.
2. **Un bug en el propio worker** (fuera de la tarea). Si eso pasara, el `Task`
   del worker terminaría con la excepción y, sin hacer nada más, asyncio solo la
   mostraría al destruirse el Task. El pool se quedaría con un worker menos para
   siempre, en silencio. Para eso, cada worker tiene un `add_done_callback`: si
   termina con una excepción fuera del apagado, se registra un error en el log y
   **se relanza un worker nuevo** en su lugar. Hay un test que lo provoca a
   propósito.

### Otras decisiones

- **El POST responde 202 Accepted**, no 201: la tarea **todavía no está
  hecha**, solo aceptada. Devuelve el header `Location: /tareas/{id}`.
- **No hay `Lock` en ningún lado.** El registro, los contadores y la cola solo
  se tocan desde corrutinas en el mismo hilo, y ninguna de esas operaciones tiene
  un `await` en el medio. El event loop solo cambia de corrutina en un `await`,
  así que cada operación es atómica sin lock. El caso más delicado es el POST:
  verifica `cola.full()` y después hace `put_nowait`, y como entre las dos no hay
  ningún `await`, ninguna otra corrutina puede quitarle el lugar. Los procesos del
  executor no comparten memoria con la app: reciben y devuelven bytes. Un test
  manda 200 tareas a 20 workers y verifica que los contadores cierren exactos.
- **httpx y no aiohttp**: tiene la misma API que `requests` en versión async y
  es la biblioteca que usamos en las clases 19 y 20. Un solo `AsyncClient`,
  creado en el `lifespan`, mantiene un pool de conexiones keep-alive con límite
  (`max_connections`) y lo comparten todas las descargas. Las respuestas se leen
  en *stream* con un tope de 50 MB por URL, para no traer un archivo enorme a
  memoria.
- **Errores de descarga por URL**: una URL caída no hace fallar la tarea. Se
  informa en su entrada (`error`, o el `estado_http` si el servidor respondió) y
  `ok` cuenta solo las respuestas 2xx/3xx.
- **Apagado ordenado.** uvicorn ya atiende SIGINT y SIGTERM con `signal.signal()`,
  así que funciona también en Windows. Lo extendí (`Servidor.handle_exit`) para
  que en el instante en que llega la señal el pool deje de aceptar tareas. El
  manejador solo levanta flags; el trabajo lo hace el `lifespan` dentro del loop.
  El apagado espera hasta `TP2_GRACIA` a las tareas en curso, cancela las que no
  llegan, deja las de la cola como `pendiente` y vuelca todo.
  - **Las señales repetidas se ignoran.** En uvicorn, una segunda Ctrl+C fuerza la
    salida y, según en qué momento llegue, saltea el `lifespan` y con él el
    volcado (lo comprobé: a veces volcaba y a veces no). Como el apagado está
    acotado (5 s para conexiones HTTP más la gracia), no hace falta forzar nada.
  - **El volcado es atómico**: se escribe un `.tmp` y se renombra con
    `os.replace`, y se hace aunque el apagado de los workers haya fallado.
  - `stop_grace_period: 30s` en el compose (más que la gracia), para que Docker
    no mande SIGKILL antes de que termine el volcado.

---

## 4. Mediciones

Todas se pueden repetir con los scripts de `scripts/`. Entorno: Windows 11 con
Docker Desktop (WSL2), 16 CPUs lógicas, Python 3.12 en el contenedor. La API con
la configuración por defecto (4 workers, 2 procesos), salvo donde se indica.

### Medición 1: concurrencia de I/O

```bash
python scripts/medir_concurrencia.py              # contra el servidor lento
python scripts/medir_concurrencia.py --internet   # contra 20 sitios reales
```

20 descargas de `http://lento:8081/demora/1` (cada una tarda 1 s), 3 corridas:

| Modo | Corrida 1 | Corrida 2 | Corrida 3 | Media |
|---|---|---|---|---|
| A. 1 tarea, `secuencial: true` | 20,11 s | 20,12 s | 20,08 s | **20,10 s** |
| B. 1 tarea, concurrente | 1,06 s | 1,05 s | 1,05 s | **1,05 s** |
| C. 20 tareas de 1 URL (4 workers) | 5,11 s | 5,08 s | 5,11 s | 5,10 s |

**Speedup de B sobre A: 19,1x.** En B, la suma de los tiempos individuales es
20,74 s, pero la tarea tarda 1,05 s: **lo que la más lenta, no la suma**.

- **A** es un `for` con `await` adentro: cada descarga empieza cuando terminó la
  anterior. Es asíncrono (no bloquea el loop: mientras tanto la API atiende), pero
  no es concurrente.
- **B** crea las 20 descargas como tasks de un `TaskGroup`. Las 20 mandan su
  pedido y quedan esperando la respuesta **al mismo tiempo**. Mientras esperan, el
  loop está libre: es la espera de red solapada (el `dormir()` del scheduler de
  la clase 18).
- **C** muestra el límite del pool: 20 tareas con 4 workers se ejecutan en
  ⌈20/4⌉ = 5 tandas de ~1 s. La concurrencia **entre** tareas está acotada por la
  cantidad de workers; la concurrencia **dentro** de una tarea (B), no.

Contra 20 sitios reales distintos:

| Modo | Corrida 1 | Corrida 2 | Corrida 3 | Media |
|---|---|---|---|---|
| Secuencial | 8,02 s | 3,62 s | 3,26 s | 4,97 s |
| Concurrente | 1,15 s | 1,36 s | 1,29 s | **1,27 s** (3,9x) |

Acá el speedup es menor, porque el concurrente nunca puede bajar del sitio **más
lento** (~1,2 s, www.um.edu.ar) y los sitios rápidos responden en 0,1 s. La primera
corrida secuencial fue más lenta porque arrancó en frío: resolución DNS y
handshakes TLS sin caché.

### Medición 2: el event loop bloqueado

```bash
TP2_HASH_EXECUTOR=ninguno docker compose up --build -d && python scripts/medir_bloqueo.py
TP2_HASH_EXECUTOR=thread  docker compose up --build -d && python scripts/medir_bloqueo.py
TP2_HASH_EXECUTOR=proceso docker compose up --build -d && python scripts/medir_bloqueo.py
```

Un `hashear` de 6 millones de iteraciones (~3,1 s de cálculo). Mientras corre,
otro cliente (con su propia conexión) pide `GET /tareas` cada 50 ms y mide cuánto
tarda cada respuesta. 3 corridas por modo:

| Dónde corre el hash | GET en reposo (p50) | GET durante el hash | Pedidos atendidos |
|---|---|---|---|
| **Sin executor** (en el loop) | 9,6 ms | **3.007 / 2.994 / 3.053 ms** (un solo GET) | 1 |
| `asyncio.to_thread` | 9,3 ms | p50 28-31 ms, máx 57-62 ms | 37-38 |
| **`ProcessPoolExecutor`** | 8,7 ms | **p50 10-12 ms**, máx 15 ms | 44-45 |

(Los ~9 ms en reposo son el reenvío de puertos de Docker Desktop en Windows. Dentro
del contenedor, el mismo GET tarda ~2 ms).

**Sin executor**, el GET que llegó durante el hash tardó **3 segundos**: lo que
duraba el cálculo. No hubo un segundo GET porque el primero no volvió hasta que
terminó el hash. Durante esos 3 s el servidor estuvo **congelado para todo el
mundo**: no atendió pedidos ni avanzaron otras tareas o timeouts, y si hubiera
llegado un SIGTERM, se habría procesado recién al final. El cálculo corre en el
mismo hilo que el event loop, y como no tiene ningún `await`, nunca le devuelve
el control. Es la "tarea egoísta" de la clase 18.

**Con `ProcessPoolExecutor`** las latencias son las mismas que en reposo, y se
atendieron 44 pedidos durante el cálculo. El hash tarda lo mismo (3,1-3,3 s): el
executor **no acelera el cálculo, saca el cálculo del loop**.

**Con threads** está en el medio: el loop responde, pero 3 veces más lento,
porque el thread del hash y el loop se pelean por el GIL. CPython le pide al
thread que suelte el GIL cada 5 ms (`sys.getswitchinterval()`), así que cada GET
tiene que esperar turnos.

Y con varios hashes a la vez aparece la otra diferencia. 4 hashes de 3 millones
(`python scripts/medir_bloqueo.py --paralelo 4 --iteraciones 3000000`, con
`TP2_PROCESOS=4`):

| Executor | Total (2 corridas) | Uno solo |
|---|---|---|
| `asyncio.to_thread` | 7,12 s / 7,14 s | — |
| `ProcessPoolExecutor` | **1,86 s / 1,97 s** | 1,64 s |

Con threads, 4 hashes tardan ~4 veces lo que tarda uno: el GIL los serializa.
Con procesos, casi lo mismo que uno, porque cada proceso tiene su propio
intérprete y su propio GIL. **Para CPU-bound: procesos.**

### Medición 3: el techo del pool

```bash
# Conviene medir DENTRO del contenedor (ver más abajo por qué)
docker compose exec -w /app/scripts api python medir_techo.py --tareas 4,8,16,32,64
TP2_WORKERS=20000 TP2_MAX_COLA=20000 docker compose up -d
docker compose exec -w /app/scripts api python medir_techo.py --tareas 100,1000,5000,10000,20000 --segundos 2
```

N tareas `esperar` mandadas de golpe (50 conexiones mandando POST a la vez).
"Ideal" es ⌈N / workers⌉ × S.

**A. Con 4 workers (el default), `esperar` de 1 s:**

| N | Envío | Total | Ideal | Exceso | GET p50 / máx |
|---|---|---|---|---|---|
| 4 | 0,01 s | 1,05 s | 1 s | 0,05 s | 3,7 / 6,7 ms |
| 8 | 0,01 s | 2,09 s | 2 s | 0,09 s | 3,4 / 10,6 ms |
| 16 | 0,01 s | 4,09 s | 4 s | 0,09 s | 3,5 / 16,0 ms |
| 32 | 0,03 s | 8,09 s | 8 s | 0,09 s | 3,6 / 28,1 ms |
| 64 | 0,07 s | 16,09 s | 16 s | 0,09 s | 3,5 / 67,5 ms |

En cuanto N supera la cantidad de workers, los tiempos **se degradan
linealmente**. El total sigue al ideal con un exceso fijo de ~0,09 s, y las
tareas esperan en la cola. **El primer techo es `TP2_WORKERS`.** Con tareas de
I/O es barato subirlo: un worker es una corrutina dormida en `cola.get()`, y no
un thread con su stack.

**B. Subiendo los workers a 20.000, `esperar` de 2 s:**

| N | Envío | POST/s | Total | Total − envío | GET p50 / máx |
|---|---|---|---|---|---|
| 100 | 0,09 s | 1.100 | 2,14 s | 2,05 s | 11 / 102 ms |
| 1.000 | 0,66 s | 1.500 | 2,73 s | 2,07 s | 13 / 73 ms |
| 5.000 | 2,99 s | 1.670 | 5,07 s | 2,08 s | 43 / 115 ms |
| 10.000 | 7,37 s | 1.360 | 9,42 s | 2,05 s | 63 / 119 ms |
| 20.000 | 16,69 s | 1.200 | 18,80 s | 2,11 s | 97 / 223 ms |

Con suficientes workers, **ejecutar** no es el problema: 20.000 tareas
concurrentes terminan ~2,1 s después del último POST (la columna "total − envío"
se mantiene en ~2 s). El límite pasa a ser **la tasa de ingreso**: ~1.100 a 1.700
POST por segundo, con el contenedor al ~130% de CPU (el event loop usa un núcleo
entero, y el resto es el cliente de la medición). La tasa **baja** y la latencia de
los GET **sube** (de 11 a 97 ms) a medida que hay más tareas corriendo, porque todo
comparte **un solo hilo**. Cada `esperar` se despierta 4 veces por segundo para
actualizar su progreso: con 20.000 activas son ~80.000 despertares por segundo,
que compiten con atender HTTP. La memoria apenas se mueve (176 → 208 MB para
20.000 tareas): el techo es la CPU del loop, no la memoria.

**C. ¿Qué pasa con 10.000 tareas de golpe y la configuración por defecto?**

```
10000 POST en 5.22s -> {202: 1008, 503: 8992}
estadisticas: workers_ocupados 4, cola_en_espera 1000, cola_capacidad 1000
GET /tareas con la cola llena: 200 en 10.1 ms
```

Lo primero que "se rompe" es **la cola, y a propósito**: se aceptan 1.008 tareas
(4 ejecutando, 4 ya terminadas y 1.000 esperando) y **las 8.992 restantes reciben
503** con `Retry-After`. La API sigue respondiendo en 10 ms. Sin `maxsize`, las
10.000 entrarían y la memoria crecería con cada pedido. Con un tráfico sostenido
mayor al que los workers pueden procesar, la memoria crecería sin límite.

**Sobre cómo medir:** la primera versión de esta medición, con httpx desde
Windows, daba ~60 POST/s. No cerraba con lo que esperaba de un servidor
asíncrono, así que lo investigué antes de reportarlo:

| Desde dónde y con qué | POST/s |
|---|---|
| httpx desde Windows (a través de Docker Desktop) | ~60 |
| httpx dentro del contenedor | ~250 |
| Cliente HTTP mínimo (`cliente_crudo.py`) dentro del contenedor | **1.100 - 2.000** |
| La app sola, llamada directo como ASGI (sin red ni cliente) | 8.400 (0,12 ms por POST) |

El reenvío de puertos de Docker Desktop sumaba ~8 ms por pedido, y el cliente
httpx (Python puro) gastaba más CPU que el propio servidor. Probé también
`uvicorn[standard]` (con `uvloop` y `httptools`) y no cambió nada: el cuello no era
el servidor. Por eso la medición 3 usa un cliente hecho con
`asyncio.open_connection` y HTTP/1.1 a mano (lo de las clases 13 y 20), y corre
dentro del contenedor. **Si el instrumento de medición es más lento que lo que se
mide, se termina midiendo el instrumento.**

---

## 5. Conceptos del curso aplicados

| Dónde | Qué | Clase |
|---|---|---|
| `pool.py`, `_worker` | Productor-consumidor: el POST produce ids, los workers consumen de una `asyncio.Queue` compartida. Es el mismo patrón de la clase 11 con corrutinas en vez de threads, y acá no hace falta lock porque el event loop no interrumpe entre `await`s | 11, 21 |
| `pool.py`, `maxsize` + 503 | Control de flujo (backpressure): la cola acotada frena al productor en vez de acumular memoria | 21 |
| `tareas.py`, `esperar` | `asyncio.sleep` cede el control: es el `dormir()` del scheduler hecho a mano con generadores. `time.sleep` sería la "tarea egoísta" que congela a todos | 18 |
| Todo el servidor | Un solo hilo y un event loop que multiplexa miles de conexiones y tareas; por debajo, `epoll` (uvloop/asyncio en Linux). La medición 3 B es el problema C10K en chico | 17, 18 |
| `tareas.py`, `descargar` | I/O de red concurrente con un cliente asíncrono reutilizado (keep-alive); `gather`/`TaskGroup` contra un `for` con `await` | 20, 21 |
| `tareas.py`, `hashear` | `run_in_executor` con `ProcessPoolExecutor`: el GIL hace que para CPU-bound sirvan procesos y no threads (medición 2) | 9, 10, 21 |
| `cpu.py` y `main.py` | `spawn` reimporta el módulo: de ahí la guarda `if __name__ == '__main__'`. Los argumentos viajan pickleados | 8, 9 |
| `pool.py`, `cancelar` y `_ejecutar` | `task.cancel()` inyecta `CancelledError` en el próximo `await`; `asyncio.timeout`; `Task.cancelling()` | 20, 21 |
| `tareas.py`, `TaskGroup` | Las hermanas se cancelan juntas, sin corrutinas huérfanas | 21 |
| `main.py`, `Servidor.handle_exit` | Manejador de señales que solo levanta flags (como en el servidor de señales de la clase 6); SIGTERM como apagado ordenado; Docker y el PID 1 | 1, 6 |
| `persistencia.py` | Escritura atómica con `os.replace` (renombrar es atómico en el mismo filesystem) | 0 (filesystem) |
| `main.py`, FastAPI | Validación con tipos (422 contra 404), 202 Accepted, 503 + `Retry-After`, `lifespan` para crear los recursos una vez | 19 |
| `registro.py` + `/eventos` | Pub/sub con una cola por suscriptor; un consumidor lento se corta para no frenar al resto | 11, 21 |
| `scripts/servidor_lento.py` | Servidor con `asyncio.start_server`, framing de HTTP por delimitador (`\r\n\r\n`) y por longitud (`Content-Length`) | 13, 19, 20 |
| `scripts/cliente_crudo.py` | Cliente con `asyncio.open_connection`, `readuntil` y `readexactly` | 13, 20 |
| `Dockerfile`, `docker-compose.yml` | Forma *exec* del `CMD` para que python sea el PID 1 y reciba el SIGTERM; `stop_grace_period`; healthcheck | 1, 2 |

### Las preguntas de la corrección

**"Mostrame dónde tu código podría bloquear el event loop."**
- `hashear` con `TP2_HASH_EXECUTOR=ninguno` bloquea **a propósito** (es la
  medición 2). Con `thread`, el loop no se bloquea pero se pelea por el GIL.
- `/estadisticas`, `/metrics` y `GET /tareas?estado=` recorren **todas** las
  tareas: son O(n) dentro del loop. Con 20.000 tareas tardan unos milisegundos.
  Con millones habría que mantener contadores incrementales.
- El volcado a JSON al apagar se escribe de forma síncrona. Es aceptable porque en
  ese momento ya no hay nada más que atender, pero con un registro enorme
  convendría `asyncio.to_thread`.
- El log a stdout es I/O síncrono (rápido, pero lo es).
- Uno que encontré y corregí en la revisión: `ProcessPoolExecutor.shutdown(wait=True)`
  esperaba dentro del loop al bloque de hash en curso. Ahora va con `asyncio.to_thread`.

**"¿Qué pasa si cancelo una tarea justo cuando está a mitad de una descarga?"**
El `CancelledError` aparece en el `await` donde está parada cada descarga (leyendo
un trozo de la respuesta). El `TaskGroup` cancela a todas las hijas y espera a que
terminen; cada `async with cliente.stream(...)` cierra su conexión al salir. La
tarea queda `cancelada` y el `DELETE` devuelve ese estado final. No queda nada
corriendo: el test `test_cancelar_descarga_a_mitad_libera_todo` lo verifica (0
tasks de la tarea y 0 conexiones abiertas en el cliente).

**"¿Por qué tu pool de workers no necesita un `Lock`?"**
Porque los workers son corrutinas en **un solo hilo**, y el event loop solo pasa
de una a otra en un `await`. Las secciones que tocan estado compartido
(`marcar_ejecutando`, `ocupados += 1`, `cola.full()` seguido de `put_nowait`) no
tienen ningún `await` en el medio, así que nadie puede interrumpirlas. En la clase
11 hacía falta lock porque un thread puede ser interrumpido por el sistema
operativo **entre cualquier par de instrucciones** (concurrencia preventiva); acá
la concurrencia es cooperativa. Y los procesos del executor no comparten memoria:
reciben y devuelven bytes.

**"Si te mando 10.000 tareas de golpe, ¿qué se rompe primero?"**
La cola, por diseño: se aceptan ~1.000 y el resto recibe **503** (medición 3 C).
Si se sube `TP2_MAX_COLA`, entran todas, y con 4 workers tardan 10.000/4 × S. Si
además se suben los workers, las 10.000 corren a la vez sin problema, y el límite
pasa a ser la CPU del event loop: el ingreso cae a ~1.400 POST/s y las respuestas
se vuelven más lentas (medición 3 B). Lo siguiente sería la memoria, porque el
registro nunca borra tareas terminadas (ver limitaciones).

**"¿Qué diferencia hay entre `asyncio.gather` y un `for` con `await` adentro?"**
El `for` con `await` es **secuencial**: la segunda corrutina recién arranca cuando
terminó la primera, y el total es la suma. `gather` (o `TaskGroup`) las **arranca
todas** y espera a que terminen, así que las esperas se solapan y el total es el de
la más lenta. Es exactamente la medición 1: **20,10 s contra 1,05 s**. Las dos
formas son "asíncronas" (ninguna bloquea el loop), pero solo la segunda es
concurrente.

**"¿Por qué `time.sleep()` en una corrutina es un bug y `asyncio.sleep()` no?"**
`time.sleep()` bloquea **el hilo**, y en asyncio hay un solo hilo para todo: el
servidor entero se congela durante ese tiempo (igual que el hash de la medición 2
sin executor). `asyncio.sleep()` no duerme el hilo: suspende **esa** corrutina y le
dice al loop "despertame en N segundos"; mientras tanto el loop sigue con las
demás. Es la diferencia entre la tarea egoísta y el `dormir()` del scheduler de la
clase 18.

---

## 6. Limitaciones conocidas

- **El estado vive en un solo proceso.** No se puede escalar con
  `uvicorn --workers N` (cada proceso tendría su propio registro y su propia cola:
  una tarea creada en uno daría 404 en otro, como vimos en la clase 19). Para eso
  haría falta un broker y un almacenamiento externos (Redis, una base de datos), que
  son justamente lo que la consigna excluye.
- **El registro crece sin límite**: las tareas terminadas nunca se borran. Con
  millones de tareas, la memoria y las consultas O(n) serían un problema. Faltaría
  una política de retención (borrar las terminadas después de X tiempo) y
  contadores incrementales.
- **El volcado no se restaura**: al arrancar se informa, pero las tareas que
  quedaron `pendiente` no se vuelven a encolar.
- **Un hash cancelado sigue calculando hasta el fin de su bloque** (~0,18 s): los
  procesos no se pueden interrumpir. Matar el proceso con `terminate()` rompería el
  pool entero.
- **Sin autenticación ni rate limiting**: cualquiera puede llenar la cola. La cola
  acotada evita que la memoria explote, pero un solo cliente puede dejar sin lugar
  a los demás.
- **`descargar` sigue redirecciones y no filtra destinos**: se le puede pedir que
  descargue URLs de la red interna (por ejemplo `http://lento:8081`, que es justo lo
  que usan las mediciones). En un servicio expuesto habría que filtrar direcciones
  privadas (SSRF).
- **La prioridad es FIFO**: no hay prioridades, así que una tarea urgente espera
  detrás de todas las anteriores.
- **El timeout no cuenta el tiempo en la cola**: una tarea puede esperar mucho
  más que su timeout antes de arrancar.

---

## 7. Lo que aprendí

> **Nota:** esta sección tiene que estar escrita con mis palabras. Este es un
> borrador para revisar y reescribir antes de entregar.

Lo que más me cambió la cabeza fue entender que asyncio no es "paralelismo
barato", sino **un solo hilo que nunca espera**. Mientras escribía el pool me di
cuenta de que no necesitaba ningún lock, y al principio desconfié; recién lo
entendí cuando lo relacioné con el scheduler de generadores de la clase 18: el loop
solo cambia de corrutina en un `await`, así que todo lo que hay entre dos `await`
es atómico. La contracara la vi en la medición 2: un solo cálculo de 3 segundos sin
`await` congeló el servidor entero para todos. Ese número, 3.007 ms contra 10 ms,
explica mejor que cualquier diagrama por qué existe `run_in_executor`.

También aprendí que cancelar bien es más difícil que ejecutar. Que una tarea se
pueda cancelar "en ejecución" me obligó a separar la tarea del worker, a usar
`TaskGroup` para no dejar descargas huérfanas y a partir el hash en bloques,
porque descubrí que un proceso que ya está calculando no se puede interrumpir:
cancelar el `await` solo descarta el resultado. Lo mismo con el apagado: suponía
que una segunda Ctrl+C se comportaba siempre igual y la prueba me mostró que no.

Y la lección que no esperaba: **medir el instrumento antes que el sistema**. La
primera medición del techo daba 60 tareas por segundo y casi la reporto así.
Al investigar resultó que el servidor procesa un POST en 0,12 ms y que lo lento
eran Docker Desktop y el cliente de pruebas. Escribir mi propio cliente con
`asyncio.open_connection` (lo de la clase 13) para medir bien fue la forma de
cerrar el círculo con la primera parte de la materia.
