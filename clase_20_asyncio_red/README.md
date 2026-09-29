# Clase 20 — Asyncio en red

Ejercicio obligatorio 3: concurrencia de clientes.

## Archivos

| Archivo | Qué es |
|---|---|
| `descargas.py` | El de la cátedra (Parte A): descargas simuladas con `asyncio.sleep` |
| `descargas_http.py` | Mi versión con **HTTP real** (`httpx.AsyncClient`) y un modo por pregunta: `secuencial`, `gather`, `semaforo N`, `cliente-por-url`, `requests`, `fallos`, `fallos-rx`, `muchas N` |
| `requirements.txt` | `httpx` y `requests` (este último solo para la pregunta 6) |

## Cómo correr

```bash
docker build -t clase20 .
docker run --rm clase20 python descargas.py
docker run --rm clase20 python descargas_http.py gather --url https://httpbin.org/delay/1
docker run --rm --ulimit nofile=64:64 clase20 python descargas_http.py muchas 200
```

Todo corrió en Ubuntu 24.04 (WSL2), Python 3.12, httpx 0.28, con mi conexión a internet.

---

## Parte A: medir la diferencia

```
12 descargas simuladas. Suma de demoras: 5.7s, la más lenta: 0.9s

  secuencial              5.79s
  gather (todas juntas)   0.85s
  con semáforo de 4       1.56s
  con timeout de 0.8s     0.80s  (1 canceladas por timeout)
```

**1. ¿Por qué `gather` tarda lo que la más lenta y no la suma?** Porque las 12
corrutinas **esperan al mismo tiempo**. Cada `await asyncio.sleep()` (o un `await`
de red) cede el control al event loop, que arranca la siguiente sin esperar a que
termine la anterior (es el `dormir()` de la clase 18). Las 12 esperas se
solapan, y `gather` termina cuando termina la última: 0,85 s ≈ la más lenta
(0,9 s).

**2. ¿Por qué el semáforo da un tiempo intermedio?** Porque deja correr solo 4 a
la vez: las 12 se procesan en "tandas" de hasta 4. Cada vez que una termina,
entra la siguiente. El tiempo total es aproximadamente la suma de las demoras
dividida por 4, limitado por las más lentas de cada tanda: 1,56 s, entre 0,85 y 5,79.

**3. Con timeout de 0,8 s** se canceló **una** (la de 0,9 s). A esa tarea,
`asyncio.timeout` le **inyecta un `CancelledError`** en el `await` en el que
estaba esperando. La corrutina se interrumpe ahí (corre sus `finally`, como se
ve en la demo de cancelación) y, al salir del bloque `async with
asyncio.timeout(...)`, el `CancelledError` se convierte en `TimeoutError`, que el
código captura y transforma en `'TIMEOUT'`. **No se espera a que termine**: se
abandona. El total queda en 0,80 s, justo el timeout.

## Parte B: con HTTP real

**4. 10 descargas secuenciales contra 10 concurrentes.** Con un endpoint que
tarda 1 s en responder (`https://httpbin.org/delay/1`):

| Modo | Tiempo |
|---|---|
| `secuencial` (httpx, un cliente) | **13,29 s** |
| `gather` (httpx, un cliente) | **2,01 s** |

**6,6 veces** más rápido. El total de `gather` es aproximadamente lo que tarda
**una** descarga (1 s de demora del servidor, más la latencia a EE. UU. y el
handshake).

Con `https://example.com` (la URL de la consigna) la diferencia es mucho menor y
ruidosa: secuencial 0,44-0,48 s, gather 0,29-0,47 s. example.com responde en ~40 ms
desde una CDN cercana, así que casi no hay espera para solapar, y el secuencial
tiene una ventaja: reutiliza **una** conexión keep-alive para las 10, mientras
que `gather` tiene que abrir 10 conexiones TCP + TLS en paralelo. La concurrencia
rinde cuando las esperas son largas comparadas con el costo de abrir conexiones.

**5. ¿Por qué el `AsyncClient` se crea una vez?** Porque el cliente es el que
tiene el **pool de conexiones**. Con HTTP/1.1 keep-alive (clase 19), una conexión
TCP + TLS ya establecida se reutiliza para los pedidos siguientes al mismo host, y
así se ahorra el handshake TCP (1 RTT) y el TLS (1-2 RTT más, y criptografía).
Un cliente nuevo por descarga empieza con el pool vacío: cada pedido paga el
handshake completo y después cierra la conexión. Con example.com, el modo
`cliente-por-url` tardó 0,39-0,45 s contra 0,26-0,29 s del semáforo con un solo
cliente. Además, crear y cerrar clientes es trabajo extra (contexto SSL, pool),
y el cliente compartido es el que aplica los **límites** de conexiones (ver la
pregunta 9).

**6. `requests` adentro de la corrutina:**

| Modo | Tiempo |
|---|---|
| `requests` dentro de `gather` | **23,22 s** |

**Es peor que el secuencial con httpx** (13,29 s). `requests.get()` es
**sincrónico**: bloquea el hilo hasta tener la respuesta, sin ningún `await`, así
que no cede el control al event loop. `gather` arranca la primera corrutina, que
bloquea el loop 2 s; recién ahí arranca la segunda, y así sucesivamente. Es
secuencial disfrazado de concurrente: la tarea egoísta de la clase 18 y el
`/async-mal` de la clase 19. Además, `requests.get()` suelto no reutiliza
conexiones (cada llamada crea su propia sesión), y por eso es todavía más lento
que el secuencial con httpx, que sí reutiliza la conexión.

## Parte C: acotar

**7. Con `Semaphore(3)`** (10 descargas de `delay/1`): **5,20 s**, con un máximo
observado de **3 descargas simultáneas**. Son 4 tandas (3 + 3 + 3 + 1) de ~1,3 s
cada una. Está entre el secuencial (13,29 s) y el `gather` libre (2,01 s).

**8. ¿Qué problemas evita acotar la concurrencia?**
1. **Agotar recursos locales**: cada conexión es un file descriptor (y memoria de
   buffers y TLS). Sin límite se llega a `ulimit -n` y todo empieza a fallar con
   `Too many open files` (pregunta 9).
2. **Saturar o ser bloqueado por el servidor remoto**: 200 conexiones simultáneas
   a un mismo host lo sobrecargan (un DoS involuntario). La mayoría de las APIs
   aplica *rate limiting* y responde **429** o banea la IP. Además está la cortesía:
   los sitios esperan pocos pedidos concurrentes por cliente.
3. También: no **saturar el ancho de banda propio** (muchas descargas grandes a la
   vez tardan cada una más y ninguna termina antes) y no disparar **timeouts** en
   cadena por pedidos que esperan en colas.

**9. 200 URLs sin semáforo.** httpx ya limita el pool a **100 conexiones** por
defecto, y eso actúa como semáforo. Para ver el problema, en el modo `muchas` le
saqué el límite (`httpx.Limits(max_connections=None)`). Con el límite de fds
normal de mi WSL (`ulimit -n` = 10240) alcanzó (200/200 en 1,76 s). Con un límite
bajo, como el `ulimit -n 1024` típico de un servidor con muchos clientes, o
directamente con 64:

```
(ulimit -n 64; python3 descargas_http.py muchas 200)
  muchas: 1.30s
  ok: 56  errores: 144
    53 x ConnectError: All connection attempts failed
    90 x ConnectError: [Errno 24] Too many open files
    1 x ConnectError: [Errno 101] Network is unreachable
```

Aparece **`[Errno 24] Too many open files`** (`EMFILE`): el proceso se quedó sin
file descriptors para abrir más sockets. Solo 56 de 200 descargas salieron bien.
(El `Network is unreachable` es un intento por IPv6, que mi WSL no tiene, y los
`All connection attempts failed` son fallos del mismo tipo que httpx resume después
de probar todas las direcciones).

## Parte D: fallos

Lista de 10 URLs con la 4.ª inválida (`https://no-existe.invalid`):

**10. Con `gather` normal:**

```
gather lanzo ConnectError a los 0.08s: [Errno -2] Name or service not known
en ese momento: 0 terminadas, 9 todavia corriendo
3s despues: 9 terminadas, 0 canceladas -> gather NO cancela a las demas, pero sus resultados se pierden
```

`gather` propaga la **primera excepción** apenas ocurre (a los 0,08 s, cuando
falla el DNS) y el `await gather(...)` termina con esa excepción. Las otras 9
**no se cancelan**: siguen corriendo en segundo plano y terminan bien, pero sus
resultados **se pierden**, porque `gather` ya no los devuelve. Quedan tareas
huérfanas trabajando para nadie. Si después se cierra el cliente o termina el
programa, se cortan a mitad de camino.

**11. Con `return_exceptions=True`:**

```
fallos-rx: 0.22s
ok: 9  errores: 1
  ('https://example.com', 200, 713)
  1 x ConnectError: [Errno -2] Name or service not known
```

`gather` **espera a todas** y devuelve una lista con un elemento por tarea, en el
mismo orden: el resultado de cada una o **la excepción como valor** en la
posición de la que falló. No se pierde nada, y el que llama decide qué hacer con
cada error.

**12. ¿Cuál para el TP2?** **`return_exceptions=True`**. En una plataforma de
tareas, las tareas son **independientes**: que una falle (una URL caída, un
archivo que no existe) no tiene que invalidar las demás ni hacer perder sus
resultados. Cada tarea tiene que terminar con su propio estado (`completada` o
`fallida` con el error guardado), y eso es exactamente lo que da
`return_exceptions=True`. El comportamiento por defecto sirve cuando las tareas
son partes de **una sola operación** que no tiene sentido si falla alguna (por
ejemplo, bajar las N partes de un archivo). Aun así, conviene cancelar
explícitamente las demás, o usar `asyncio.TaskGroup`, que sí las cancela.
Hay que tener cuidado con una cosa: con `return_exceptions=True` hay que
**revisar** la lista buscando excepciones, porque si no se chequea, los errores
pasan desapercibidos.

## Checklist de la consigna

- [x] Secuencial contra `gather` con números propios (simulado y HTTP real)
- [x] Por qué `gather` tarda lo que la más lenta
- [x] Descargas reales con `httpx` y `AsyncClient` reutilizado (más la comparación con un cliente por descarga)
- [x] `requests` dentro de una corrutina (23,22 s: bloquea el loop)
- [x] Semáforo implementado y medido (máximo 3 simultáneas, 5,20 s)
- [x] Dos (tres) problemas que evita acotar la concurrencia
- [x] `return_exceptions=True` probado y elegido para el TP2
