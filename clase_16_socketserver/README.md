# Clase 16 — socketserver

Ejercicio obligatorio 3: los mixins.

## Archivos

| Archivo | Para qué |
|---|---|
| `mixins_fuente.py` | Partes A y B: métodos de cada mixin, quién resuelve `process_request` y los dos MRO |
| `orden_mixins.py` | Parte B: el mismo servidor lento (2 s por cliente) con el mixin bien puesto (`correcto`) y al revés (`alreves`) |
| `clientes_lentos.py` | Conecta N clientes a la vez y mide cuánto tardan en total |
| `eco_tcp.py` | El de la cátedra (Parte C), con un flag `--sin-daemon` agregado para la Parte E |
| `comandos_contador.py` | Parte D: servidor de comandos (basado en `comandos.py`) con un contador **global**, con threads o con `--fork` |

## Cómo correr

```bash
docker build -t clase16 .
docker run --rm -it --name ss clase16 bash
python mixins_fuente.py
python orden_mixins.py alreves & python clientes_lentos.py 8080 2
python comandos_contador.py --fork &  nc localhost 8080     # escribir CONTADOR
```

Todo lo de abajo corrió en Linux (Ubuntu 24.04, Python 3.12).

---

## Parte A: leer el código fuente

```
ThreadingMixIn: ['process_request_thread', 'process_request', 'server_close']
ForkingMixIn: ['collect_children', 'handle_timeout', 'service_actions', 'process_request', 'server_close']

== process_request: quien lo define
  BaseServer      lo define: True
  TCPServer       lo define: False
  ThreadingMixIn  lo define: True
  ForkingMixIn    lo define: True
```

**1.** `ThreadingMixIn` define **3** métodos (además de los atributos
`daemon_threads`, `block_on_close` y `_threads`). El que importa es
**`process_request`**: es el único punto donde cambia el comportamiento. Los otros
dos le dan soporte: `process_request_thread` es lo que corre dentro del thread,
y `server_close` hace el `join` de los threads al cerrar.

**2.** `TCPServer` no define `process_request`: lo hereda de `BaseServer`, que
hace `finish_request()` (crea el handler y corre `handle()`) y
`shutdown_request()` **en el mismo hilo que hace el `accept`**. Mientras un
cliente está siendo atendido, el servidor no acepta otro. La versión de
`ThreadingMixIn` crea un `threading.Thread(target=process_request_thread)`, lo
arranca y **vuelve enseguida**, así que el bucle de `serve_forever` vuelve a
aceptar. El thread hace lo mismo que hacía `BaseServer` (`finish_request` +
`shutdown_request`) y además captura las excepciones con `handle_error`.

**3. ¿Dónde cosecha `ForkingMixIn`?** En **`collect_children()`**. Guarda los
PIDs de sus hijos en `active_children` y, para cada uno, hace
`os.waitpid(pid, os.WNOHANG)`. Lo llama desde:
- `service_actions()`, que `serve_forever` ejecuta **en cada vuelta del bucle**
  (como mínimo cada `poll_interval` = 0,5 s);
- `handle_timeout()` y `server_close()` (este último bloqueante si `block_on_close`);
- y cuando se supera `max_children` (40) hace `waitpid` **bloqueante** hasta bajar
  del límite. Eso además sirve de control de carga.

**¿Por qué no hay zombies como en la clase 14?** Porque **no usa `SIGCHLD`**:
hace polling. No depende de que lleguen señales (que se fusionan y se pierden),
sino que en cada vuelta recorre la lista de hijos y pregunta por cada uno. Un
hijo que termina puede quedar zombie como mucho hasta la siguiente vuelta del
bucle (~0,5 s), nunca de forma permanente.

## Parte B: el orden importa

```
Correcto  ['Correcto', 'ThreadingMixIn', 'TCPServer', 'BaseServer', 'object']
          process_request -> ThreadingMixIn
          server_close    -> ThreadingMixIn
AlReves   ['AlReves', 'TCPServer', 'BaseServer', 'ThreadingMixIn', 'object']
          process_request -> BaseServer
          server_close    -> TCPServer
```

**4.** En `Correcto`, `ThreadingMixIn` aparece **antes** que `TCPServer` y
`BaseServer`, así que su `process_request` es el primero que encuentra Python. En
`AlReves` aparece **después** de `BaseServer`, que ya define `process_request`,
así que la versión del mixin nunca se usa. El mixin está en la jerarquía pero no
tiene ningún efecto.

**5.** Dos clientes lentos (2 s cada uno) con `clientes_lentos.py`:

```
[correcto] ['Correcto', 'ThreadingMixIn', 'TCPServer'] en :9301
  atendiendo 46494 en Thread-1 (process_request_thread)
  atendiendo 46498 en Thread-2 (process_request_thread)
  cliente 0: b'CLIENTE 0' en 2.00s
  cliente 1: b'CLIENTE 1' en 2.00s
Total para 2 clientes: 2.01s

[alreves] ['AlReves', 'TCPServer', 'BaseServer'] en :9301
  atendiendo 58612 en MainThread
  atendiendo 58620 en MainThread
  cliente 0: b'CLIENTE 0' en 2.00s
  cliente 1: b'CLIENTE 1' en 4.01s
Total para 2 clientes: 4.01s
```

`Correcto` atiende en paralelo, cada cliente en su thread: 2 s en total.
`AlReves` atiende todo en `MainThread`, **uno detrás del otro**: el segundo
cliente tarda 4 s.

**6.** No lanza **ningún error**, ni al definir la clase ni al correr. Por eso es
peligroso: el código "tiene" `ThreadingMixIn`, las pruebas con un cliente
funcionan, y el problema aparece recién en producción con carga, como un servidor
lento sin ninguna pista de por qué. Hay que acordarse de que **los mixins van
primero** (a la izquierda) o, más seguro, usar las clases ya armadas
(`ThreadingTCPServer`, `ForkingTCPServer`).

## Parte C: threads contra procesos

5 clientes conectados a la vez a `eco_tcp.py`:

```
threads (python3 eco_tcp.py):
+ 127.0.0.1:43222  (pid=4800 hilo=Thread-1 (process_request_thread))
+ 127.0.0.1:43196  (pid=4800 hilo=Thread-2 (process_request_thread))
...
+ 127.0.0.1:43194  (pid=4800 hilo=Thread-5 (process_request_thread))
threads del proceso (ls /proc/PID/task | wc -l): 6
hijos: 0

fork (python3 eco_tcp.py --fork):
+ 127.0.0.1:42798  (pid=4978 hilo=MainThread)
+ 127.0.0.1:42808  (pid=4979 hilo=MainThread)
...
+ 127.0.0.1:42836  (pid=4982 hilo=MainThread)
threads del proceso: 1
hijos (ps --ppid):
 4978 S    python3
 4979 S    python3
 4980 S    python3
 4981 S    python3
 4982 S    python3
```

**7.** Con threads, el **PID es siempre el mismo** y cambia el hilo
(`Thread-1` … `Thread-5`). Con fork, **cada cliente tiene su PID** y todos corren
en `MainThread` (cada proceso hijo tiene un único hilo).

**8.** Con `--fork`, **5 PIDs distintos** (4978-4982), los 5 hijos que muestra
`ps --ppid`, todos en estado `S` (dormidos en `recv`, esperando datos).

**9.** Con threads, **6** entradas en `/proc/PID/task`: el hilo principal (el
de `serve_forever`) más un thread por cliente.

## Parte D: el estado no se comparte igual

4 conexiones seguidas, cada una manda `PID` y `CONTADOR`:

```
ThreadingTCPServer                      ForkingTCPServer
pid=4990 hilo=Thread-1 ...              pid=5009 hilo=MainThread
Conexiones totales: 1                   Conexiones totales: 1
pid=4990 hilo=Thread-2 ...              pid=5012 hilo=MainThread
Conexiones totales: 2                   Conexiones totales: 1
pid=4990 hilo=Thread-3 ...              pid=5016 hilo=MainThread
Conexiones totales: 3                   Conexiones totales: 1
pid=4990 hilo=Thread-4 ...              pid=5019 hilo=MainThread
Conexiones totales: 4                   Conexiones totales: 1
```

**10.** Con threads funciona porque **todos los threads están en el mismo
proceso** y comparten la memoria: la variable global `contador` es una sola, y
cada handler incrementa la misma. Hace falta el `Lock`, porque `+=` no es atómico
(clase 11).

**11.** Con fork siempre devuelve **1**. Cada conexión es un proceso hijo creado
con `fork()`, que recibe una **copia** de la memoria del padre, con `contador =
0` porque el padre nunca lo incrementa: el `setup()` corre en el hijo. El hijo
incrementa **su** copia a 1, responde y muere, y el incremento muere con él. El
padre y los demás hijos nunca lo ven. (El `Lock` tampoco sirve de nada: también
es una copia por proceso).

**12.** Hace falta **memoria compartida entre procesos** de la clase 9:
`multiprocessing.Value('i', 0)` (con su `get_lock()`), creado **antes** de
`serve_forever` para que los hijos lo hereden. Otra opción es un `Manager` si
el estado es más complejo (un dict de clientes activos, por ejemplo), a costa de
pasar cada acceso por un proceso servidor.

## Parte E: daemon_threads

Servidor de threads con un cliente conectado (`nc`, que se queda abierto 8 s) y
SIGINT (lo mismo que Ctrl+C) apenas conecta:

```
daemon_threads = True:   termino .113s despues del SIGINT

daemon_threads = False:  a los 4s del SIGINT el servidor SIGUE vivo
                         termino recien cuando el cliente cerro: 6.99s despues del SIGINT
```

**13.** Sin `daemon_threads = True`, Ctrl+C muestra "Servidor detenido" pero **el
proceso no termina**: se queda colgado hasta que el cliente se desconecta.
`serve_forever` corta, y al salir del `with` se llama a `server_close()`, que en
`ThreadingMixIn` hace `self._threads.join()`: espera a cada thread de cliente
(`block_on_close = True` por defecto). Aunque se sacara ese `join`, el
intérprete, al salir, también espera a todos los threads que no son daemon. Un
cliente que deja la conexión abierta impide apagar el servidor.

**14.** Con `daemon_threads = True`, los threads de los clientes son daemon: no
se registran para el `join` y el intérprete no los espera al salir. El proceso
termina de inmediato (0,11 s) y las conexiones abiertas se cortan de golpe.
Es lo que se quiere al apagar con Ctrl+C. La contra es que un cliente a mitad
de una respuesta la recibe cortada; para un apagado prolijo habría que avisarles
a los handlers y esperarlos con un tiempo límite.

## Checklist de la consigna

- [x] Qué método sobrescribe cada mixin (`process_request`)
- [x] Dónde cosecha los hijos `ForkingMixIn` (`collect_children` desde `service_actions`, por polling)
- [x] Los dos MRO y la diferencia
- [x] Orden invertido: no da error pero no concurre (2 s contra 4 s)
- [x] PIDs con forking (5) y threads con threading (6 tasks)
- [x] Por qué el estado compartido funciona con threads y no con procesos
- [x] Efecto de `daemon_threads` (0,11 s contra esperar al cliente)
