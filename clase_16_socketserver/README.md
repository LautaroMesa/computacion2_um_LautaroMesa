# Clase 16 — socketserver

Ejercicio obligatorio 2: los mixins (numeración del repo actualizado de la cátedra).

## Archivos

| Archivo | Para qué |
|---|---|
| `mixins_fuente.py` | Partes A y B: métodos de cada mixin, quién provee `process_request` y los dos MRO |
| `orden_mixins.py` | Parte B: el mismo servidor lento (2 s por cliente) en tres versiones: `secuencial` (sin mixin), `correcto` y `alreves` |
| `clientes_lentos.py` | Conecta N clientes a la vez y mide cuánto tardan en total |
| `comandos_contador.py` | Parte C: contador de conexiones con threads, con `--fork` y con `--fork --value` (`multiprocessing.Value`) |
| `eco_tcp.py` | El de la cátedra, con un flag `--sin-daemon` agregado para la Parte D |

## Cómo correr

```bash
docker build -t clase16 .
docker run --rm -it --name ss clase16 bash
python mixins_fuente.py
python orden_mixins.py alreves & python clientes_lentos.py 8080 2
python comandos_contador.py --fork --value &  nc localhost 8080     # escribir CONTADOR
```

Todo lo de abajo corrió en Linux (Ubuntu 24.04, Python 3.12).

---

## Parte A: leer el código

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
`daemon_threads`, `block_on_close` y `_threads`). El que produce la
concurrencia es **`process_request`**. Los otros dos le dan soporte:
`process_request_thread` es lo que corre dentro del thread, y `server_close`
hace el `join` de los threads al cerrar.

**2.** El `process_request` de `BaseServer` hace `finish_request()` (crea el handler
y corre `handle()`) y `shutdown_request()` **en el mismo hilo que hace el
`accept`**: mientras atiende a un cliente, el servidor no acepta otro. El del
mixin crea un `threading.Thread(target=process_request_thread)`, lo arranca y
**vuelve enseguida**, así que `serve_forever` vuelve a aceptar. El thread hace lo
mismo que hacía `BaseServer` (`finish_request` + `shutdown_request`) y además
captura las excepciones con `handle_error`.

**3. ¿Dónde cosecha `ForkingMixIn`?** En **`collect_children()`**. Guarda los
PIDs de sus hijos en `active_children` y, para cada uno, hace
`os.waitpid(pid, os.WNOHANG)`. Lo llama desde:
- `service_actions()`, que `serve_forever` ejecuta **en cada vuelta del bucle**
  (como mínimo cada `poll_interval` = 0,5 s);
- `handle_timeout()` y `server_close()` (este último bloqueante si `block_on_close`);
- y cuando se supera `max_children` (40) hace `waitpid` **bloqueante** hasta bajar
  del límite. Eso además sirve de control de carga.

**¿Por qué no hay zombies como en la clase 14?** Porque **no usa `SIGCHLD`**:
hace polling. No depende de señales que se fusionan y se pierden, sino que en
cada vuelta recorre la lista de hijos y pregunta por cada uno. Un hijo que
termina puede quedar zombie como mucho hasta la siguiente vuelta del bucle
(~0,5 s), nunca de forma permanente.

**4. ¿Cuánto código propio tiene `ThreadingTCPServer`?** Ninguno:

```python
class ThreadingTCPServer(ThreadingMixIn, TCPServer): pass
```

Una línea y un `pass` (lo mismo `ForkingTCPServer`). Todo el comportamiento
sale de combinar las dos bases en el orden correcto.

## Parte B: el orden

```
Correcto  ['Correcto', 'ThreadingMixIn', 'TCPServer', 'BaseServer', 'object']
          process_request -> ThreadingMixIn
          server_close    -> ThreadingMixIn
AlReves   ['AlReves', 'TCPServer', 'BaseServer', 'ThreadingMixIn', 'object']
          process_request -> BaseServer
          server_close    -> TCPServer
```

(En la consigna nueva se llaman `Bien` y `Mal`; en mi código, `Correcto` y `AlReves`).

**5.** En `Correcto`, `ThreadingMixIn` aparece **antes** que `TCPServer` y
`BaseServer`. En `AlReves` aparece **después** de `BaseServer`, que ya define
`process_request`.

**6.** En `Correcto` lo provee **`ThreadingMixIn`**; en `AlReves`,
**`BaseServer`**. La versión del mixin nunca se usa: está en la jerarquía pero no
tiene ningún efecto.

**7.** Dos clientes lentos (2 s cada uno) con `clientes_lentos.py`:

| Servidor | Hilo que atiende | Cliente 0 | Cliente 1 | Total |
|---|---|---|---|---|
| `secuencial` (`TCPServer` solo) | `MainThread` las dos veces | 2,01 s | 4,01 s | **4,01 s** |
| `correcto` | `Thread-1`, `Thread-2` | 2,01 s | 2,01 s | **2,01 s** |
| `alreves` | `MainThread` las dos veces | 2,01 s | 4,01 s | **4,01 s** |

`Correcto` atiende en paralelo. `AlReves` se comporta **exactamente igual que
el secuencial**, con el mismo tiempo y el mismo hilo, aunque "tenga"
`ThreadingMixIn`.

**8.** No lanza **ningún error**, ni al definir la clase ni al correr. Por eso es
peligroso: el código parece concurrente, las pruebas con un cliente funcionan, y
el problema recién aparece con carga, como un servidor lento sin ninguna pista
de por qué. **Los mixins van primero** (a la izquierda), o conviene usar las clases
ya armadas (`ThreadingTCPServer`, `ForkingTCPServer`).

## Parte C: forking y memoria

4 conexiones seguidas; cada una manda `PID` y `CONTADOR`:

```
threads                         --fork                          --fork --value
pid=5360 hilo=Thread-1 ...      pid=5379 hilo=MainThread        pid=5394 hilo=MainThread
Conexiones totales: 1           Conexiones totales: 1           Conexiones totales: 1
pid=5360 hilo=Thread-2 ...      pid=5382 hilo=MainThread        pid=5397 hilo=MainThread
Conexiones totales: 2           Conexiones totales: 1           Conexiones totales: 2
pid=5360 hilo=Thread-3 ...      pid=5385 hilo=MainThread        pid=5400 hilo=MainThread
Conexiones totales: 3           Conexiones totales: 1           Conexiones totales: 3
pid=5360 hilo=Thread-4 ...      pid=5388 hilo=MainThread        pid=5403 hilo=MainThread
Conexiones totales: 4           Conexiones totales: 1           Conexiones totales: 4
```

**9.** Con `ForkingTCPServer`, `CONTADOR` devuelve **siempre 1**.

**10. Por qué (clase 4).** `fork()` crea un proceso hijo con una **copia** del
espacio de memoria del padre (copy-on-write). El contador vive en el objeto
servidor, en la memoria del padre, y el padre nunca lo incrementa: `setup()` corre
en el hijo. Cada hijo arranca con su copia en `0`, la incrementa a `1`, responde
y muere, y ese cambio muere con él. El padre y los demás hijos nunca lo ven. El
`threading.Lock` tampoco sirve: también es una copia por proceso. Con threads
funciona porque todos comparten la memoria del mismo proceso.

**11. El arreglo: `multiprocessing.Value`** (clase 9). Está en
`comandos_contador.py --fork --value` (clase `ContadorCompartido`):

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.contador = multiprocessing.Value('i', 0)

def incrementar(self):
    with self.contador.get_lock():     # += son dos accesos: hace falta el lock
        self.contador.value += 1
```

Con 4 conexiones cuenta 1, 2, 3, 4. Además lo probé con **200 conexiones
concurrentes** (50 a la vez) y una más para consultar:

```
Conexiones totales: 201 (esperado 201)
```

**12. ¿Dónde se crea el `Value`?** En el **`__init__` del servidor**, que corre en
el padre **antes** del primer `fork()`. `Value` reserva memoria compartida
(un `mmap` anónimo compartido), y los hijos creados después heredan ese mismo
mapeo: todos escriben en las mismas páginas físicas. Si se creara en el handler,
cada hijo reservaría su **propio** `Value` nuevo después del fork, que nadie más
ve, y el contador volvería a dar siempre 1.

## Parte D: daemon_threads

Servidor de threads (`eco_tcp.py`) con un cliente conectado (`nc`, abierto 8 s) y
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
Es lo que se quiere al apagar con Ctrl+C. La contra es que un cliente a mitad de
una respuesta la recibe cortada; para un apagado prolijo habría que avisarles a
los handlers y esperarlos con un tiempo límite.

## Extra: threads contra procesos (de la versión anterior de la consigna)

5 clientes conectados a la vez a `eco_tcp.py`. Con threads: **un solo PID** y
6 entradas en `/proc/PID/task` (el hilo principal más uno por cliente). Con
`--fork`: **5 PIDs distintos**, los 5 hijos de `ps --ppid`, todos en `MainThread`
y en estado `S` (esperando datos en `recv`).

## Checklist de la consigna

- [x] Qué método sobrescribe cada mixin (`process_request`)
- [x] Dónde cosecha los hijos `ForkingMixIn` (`collect_children` desde `service_actions`, por polling)
- [x] Los dos MRO y qué clase provee `process_request` en cada uno
- [x] Orden invertido: no da error pero no concurre
- [x] Diferencia medida entre secuencial y concurrente (4,01 s contra 2,01 s)
- [x] Por qué el estado compartido falla con forking
- [x] Versión con `multiprocessing.Value` (201/201 con 200 conexiones concurrentes)
- [x] Efecto de `daemon_threads` (0,11 s contra esperar al cliente)
