# TP1 — Monitor de Procesos y Threads

Computación II — Universidad de Mendoza — 2026
Alumno: Lautaro Mesa (legajo 64060)

## 1. Descripción general

Monitor de procesos Linux en tiempo real, estilo `htop`, que lee `/proc` directamente
(sin `psutil`). Es un sistema **multiproceso**: un recolector/agregador central mantiene
un snapshot compartido en memoria, 7 analizadores independientes (uno por dimensión:
resumen, memoria, FDs, threads, señales, scheduling, sistema) lo actualizan cada uno a
su propio ritmo, y un proceso Display muestra los datos con una TUI (`rich`) que se puede
navegar y reconfigurar en caliente.

### Cómo correr

```bash
docker compose up --build
```

Esto levanta todo el sistema (Recolector, 7 analizadores, señales, Display). **Para
interactuar de verdad con la TUI (teclado)**, usar en cambio:

```bash
docker compose run --rm --build monitor
```

`docker compose up` está pensado para **seguir logs** (como `tail -f` de varios
servicios a la vez), así que procesa la salida como texto línea por línea para poder
mezclarla y prefijarla con el nombre del servicio (`monitor-1 |`). Una TUI de pantalla
completa no imprime líneas: manda secuencias ANSI de posicionamiento de cursor para
repintar la misma región una y otra vez, sin saltos de línea reales entre repintados —
un modelo incompatible de raíz con el de "seguir logs". El resultado es que la pantalla
titila sin parar (confirmado que `--no-log-prefix` tampoco lo arregla: el problema no es
el prefijo, es el procesamiento línea por línea en sí). `docker compose run` en cambio
conecta la terminal **directo**, sin ese procesamiento de logs de por medio — mismo
código (`main.py`, `display.py`) corriendo igual en ambos casos, la única diferencia es
cómo el *cliente* de Compose maneja la salida antes de mostrarla. Más detalle en la
sección 5.

### Uso

- `1`-`7` o `r`/`m`/`f`/`t`/`s`/`p`/`g`: cambiar de vista (Resumen/Memoria/FDs/Threads/
  Señales/Scheduling/Sistema)
- `↑` `↓`: navegar la lista de procesos
- `Enter`: pin/unpin del proceso seleccionado (no se mueve aunque cambie el orden)
- `/`: filtrar por nombre de comando
- `u`: filtrar por usuario
- `c`: alternar orden (CPU% → RSS → PID → CPU%...)
- `+` / `-`: ajustar el intervalo de refresco de la vista activa (respeta el mínimo de
  `config.json`)
- `h` / `?`: ayuda
- `q`: salir limpiamente (dispara el mismo shutdown que `Ctrl+C`)

### Señales del monitor (se mandan desde afuera del contenedor)

```bash
docker kill --signal=SIGUSR1 <container>   # dump del snapshot a dump_<timestamp>.json
docker kill --signal=SIGHUP  <container>   # recarga config.json (intervalos)
docker kill --signal=SIGUSR2 <container>   # toggle modo verbose
docker kill --signal=SIGINT  <container>   # shutdown limpio (equivalente a Ctrl+C)
```

## 2. Diagrama de arquitectura

```
                    ┌──────────────┐
                    │  RECOLECTOR  │   lista /proc (os.listdir) cada 1s
                    │   (1 proc)   │   y publica la lista de PIDs
                    └──────┬───────┘
                           │ escribe snapshot['_pids']
                           ▼
                        ┌───────────────────────────────────┐
                        │      SNAPSHOT (Manager.dict)       │
                        │  _pids (interno, no es una vista)  │
                        │  resumen | memoria | fds | threads │
                        │  senales | scheduling | sistema    │
                        └───────▲───────────────────▲────────┘
                     escriben   │                    │  lee
           ┌──────────┬─────────┼──────────┬─────────┴──────┐
           │          │         │          │                │
      ┌────▼───┐ ┌────▼───┐┌────▼───┐┌─────▼──┐   ...   ┌────▼─────┐
      │resumen │ │memoria ││  fds   ││threads │  (7 en   │ display  │
      │  2s    │ │  3s    ││  5s    ││  2s    │  total)  │  (TUI,   │
      └────────┘ └────────┘└────────┘└────────┘          │  rich)   │
                                                           └────┬─────┘
       cada analizador LEE snapshot['_pids'] en vez de           │ 'q' → SIGINT
       listar /proc por su cuenta; cada uno es 1 Process          │ al padre
       independiente, con su propio Value('d') de intervalo       │
                                                                 │
   ┌──────────────────────────────── main.py (orquestador) ◄────┘
   │  - crea el Manager y el snapshot inicial
   │  - crea 1 Value por vista (intervalo compartido, editable con +/-)
   │  - lanza Recolector + 7 analizadores + Display como Process hijos
   │  - self-pipe: traduce señales del SO en acciones (senales.py)
   │        SIGINT/SIGTERM -> terminate() a los hijos, shutdown limpio
   │        SIGHUP  -> relee config.json, actualiza los Value de intervalo
   │        SIGUSR1 -> vuelca el snapshot a dump_<ts>.json
   │        SIGUSR2 -> toggle de un Value('b') de verbose
   └─────────────────────────────────────────────────────────────────
```

El Recolector es el único que llama a `os.listdir('/proc')`. Cada analizador toma esa
lista de PIDs del snapshot y lee `/proc/<pid>/...` para su dimensión específica (memoria,
FDs, threads, etc.), arma su lista/dict de resultados, y publica una entrada
`{'datos': ..., 'ts': ...}` en el snapshot compartido. El Display sólo lee el snapshot;
nunca toca `/proc` directamente ni corre lógica de recolección.

## 3. Decisiones de diseño

**¿Por qué `multiprocessing.Manager` para el snapshot y no otra cosa?**
El snapshot necesita guardar estructuras heterogéneas y anidadas (listas de dicts, dicts
con distinto shape por vista) que cambian de tamaño constantemente (la cantidad de
procesos varía). `Value`/`Array` sirven para tipos de tamaño fijo (un float, un booleano,
un array de C), no para "un dict con listas adentro". `Manager.dict` levanta un proceso
servidor aparte y expone proxies: cuando escribís `snapshot[vista] = {...}`, en realidad
estás mandando esos datos (pickleados) por IPC al servidor. Es más lento que memoria
compartida cruda, pero es la herramienta correcta para datos de forma variable. Prueba
concreta de esto: al correr `main.py` standalone durante el desarrollo, aparecía un PID
extra en el propio snapshot de "resumen" (con 4 threads) que no había lanzado
explícitamente — era el proceso servidor del `Manager`.

**¿Por qué el Recolector distribuye los PIDs por el `Manager` y no por `Queue`/`Pipe`?**
`Queue` y `Pipe` modelan comunicación **punto a punto**: un mensaje puesto en la cola lo
consume UN receptor (el primero que llegue), y si lo necesitan varios receptores hay que
duplicar el `put()` por cada uno. Acá el caso es justo al revés: el Recolector necesita
**difundir** (broadcast) la misma lista de PIDs a los 7 analizadores por igual, y cada uno
la va a leer en un momento distinto (cada uno tiene su propio intervalo). Para ese patrón,
memoria compartida de lectura libre (el `Manager.dict` que ya usábamos para el snapshot)
encaja mejor: el Recolector escribe `snapshot['_pids']` una vez por vuelta, y los 7
analizadores la leen cuando les toca, sin coordinarse entre sí ni consumir el dato (a
diferencia de `Queue.get()`, leer del `Manager` no "vacía" nada).

**¿Por qué `Value` sí para los intervalos?**
Cada intervalo es un único float que cambia con `+`/`-` desde el Display y se lee desde
el analizador correspondiente en cada vuelta del loop. Es exactamente el caso de uso de
`Value`: un escalar de tamaño fijo, compartido entre dos procesos, sin necesidad de la
sobrecarga de un `Manager` para esto.

**¿Cómo se manejan las race conditions?**
La única estructura realmente compartida y mutable es el snapshot. Se evita el problema
de raíz: cada analizador es el único escritor de SU vista (`snapshot['memoria']` sólo lo
escribe el analizador de memoria), así que no hay dos procesos escribiendo la misma clave
al mismo tiempo. Dentro de `agregador.publicar()`, la entrada se reasigna completa de una
sola vez (`snapshot[vista] = {...}`) en lugar de mutar campo por campo — el
`Manager.dict.__setitem__` es una sola llamada RPC atómica al proceso servidor, así que el
Display nunca puede leer una entrada a medio escribir. Los `Value` de intervalo se tocan
con `.get_lock()` al escribir desde el Display, aunque en la práctica una sola escritura
de un float ya es atómica a nivel de la primitiva.

**¿Por qué esos intervalos por defecto?**
Los define la consigna (2s para vistas "calientes" como resumen/threads/sistema, 5-10s
para vistas más pesadas de calcular o menos volátiles como FDs/señales/scheduling). Tienen
sentido además por costo: iterar `/proc/<pid>/maps` o `/proc/<pid>/task/*` para TODOS los
procesos es notablemente más caro que leer un solo `/proc/<pid>/stat`, así que conviene
refrescarlo con menos frecuencia.

**Señales: patrón self-pipe.**
Los handlers de señal no pueden hacer trabajo real (I/O con buffers no atómicos, tomar
locks, hablar con el `Manager`) porque pueden interrumpir al programa en cualquier punto,
incluso a mitad de una operación que use ese mismo recurso (riesgo de deadlock o de
corromper datos). El handler instalado en `senales.py` hace lo único garantizado seguro
por POSIX: un `os.write()` de 1 byte a un pipe interno. El loop principal de `main.py`
espera ese pipe con `select()` y recién ahí, en contexto normal (no de signal handler),
decide qué hacer según el número de señal recibido.

**¿Por qué cada analizador ignora SIGINT?**
Los procesos hijos comparten grupo de procesos con el padre (no se les hace `setsid()`),
así que un `Ctrl+C` real en la terminal les llega a TODOS al mismo tiempo, no sólo al
proceso principal. Sin `agregador.ignorar_sigint()` al inicio de cada `correr()`, cada hijo
levantaría un `KeyboardInterrupt` con su propio traceback. La decisión de cuándo y cómo
cerrar el sistema es exclusiva del proceso principal (vía el self-pipe); a los hijos los
para explícitamente con `Process.terminate()` (SIGTERM).

**¿Por qué Display abre `/dev/tty` a mano en vez de usar `sys.stdin`?**
Hallazgo durante las pruebas: `multiprocessing` le cierra el `stdin` heredado a **todo**
proceso hijo y lo reemplaza por `/dev/null` (para que un hijo no compita por leer del
mismo teclado que el padre "por las dudas"). Como Display corre como
`multiprocessing.Process`, su `sys.stdin` nunca ve la terminal real, sin importar si el
contenedor la tiene o no — el síntoma era idéntico a "no hay terminal interactiva" incluso
corriendo `docker run -it` en una consola real. La solución es el idiom clásico de Unix
para este caso: abrir `/dev/tty`, el nombre especial que siempre apunta a la terminal de
control del proceso que lo abre, sin pasar por `stdin`. Como Display no llama a `setsid()`,
sigue en la misma sesión que el proceso principal, así que `/dev/tty` resuelve al mismo
pty que le dio Docker al contenedor.

**¿Por qué `rich` y no `curses`?**
`curses` es la opción "clásica" (la usa `htop`) y no requiere dependencias, pero mezclar
manejo de pantalla y de teclado en la misma API vuelve más difícil separar "estado de la
UI" de "entrada de teclado" con claridad. `rich.Live` deja definir el render como una
función pura del estado (`snapshot` + `Estado` → `Group` de tablas/paneles) y refrescar
manualmente, lo que combina bien con el resto del diseño (todo el estado vive afuera del
loop de renderizado). El costo es que `rich` no incluye lectura de teclado, así que hay
que armarla a mano con `termios`/`tty` en un hilo aparte (explícitamente permitido por la
consigna sólo para esto).

**¿Por qué la cantidad de filas de la tabla de procesos se calcula en runtime
(`console.size.height`) en vez de ser un número fijo?**
Bug real encontrado con un test automatizado (un pty simulado enviando teclas reales al
`main.py` real): en una terminal de 24 filas, una tabla de 20 procesos fijos + el panel
de detalle + la barra de estado no entraban en pantalla, y `rich.Live` con `screen=True`
corta todo lo que no entra **sin avisar** — el panel de Estado (con el pin, los filtros y
la ayuda de teclas) desaparecía en silencio. La cantidad de filas visibles ahora se
calcula a partir de `console.size.height`, dejando siempre lugar fijo para el panel de
detalle y la barra de estado.

## 4. Conceptos del curso aplicados

- **Clase 3 (procesos, `/proc`)**: todo `procfs.py` — parsear `/proc/<pid>/stat`,
  `/proc/<pid>/status`, `/proc/<pid>/maps` a mano, sin ninguna librería que abstraiga el
  acceso al kernel.
- **Clase 4 (fork, exec, wait, zombies)**: la vista Sistema cuenta zombies mirando el
  campo `state == 'Z'` de `/proc/<pid>/stat` — un zombie es un proceso que terminó pero
  cuyo padre todavía no llamó a `wait()`, así que el kernel mantiene su entrada en
  `/proc` con ese estado. También: la disposición de señales (SIGINT) se hereda al hacer
  `fork()`, lo que explica por qué hubo que ignorarla explícitamente en cada analizador
  hijo (ver sección 3).
- **Clase 5 (pipes, FDs)**: la vista FDs lista `/proc/<pid>/fd/*` con `os.readlink()` para
  ver a qué apunta cada descriptor (socket, pipe, archivo, tty). El self-pipe de señales
  también es, literalmente, un pipe (`os.pipe()`) usado como mecanismo de sincronización.
- **Clase 6 (señales)**: patrón self-pipe async-signal-safe para las 5 señales obligatorias
  (ver sección 3), y el problema concreto de qué puede/no puede hacer un handler.
- **Clase 7 (mmap / memoria compartida)**: `multiprocessing.Value` usa memoria mapeada con
  `mmap` por debajo para compartir un escalar sin pasar por un proceso servidor — por eso
  se usa para los intervalos en vez de meterlos en el `Manager`.
- **Clase 8-9 (multiprocessing, Manager)**: arquitectura completa de Recolector + 7
  analizadores + agregador + `Manager.dict` como snapshot compartido (ver sección 3). El
  propio proceso servidor del `Manager` fue una prueba viva de esto: apareció como un PID
  extra no lanzado explícitamente al inspeccionar el snapshot.
- **Clase 10 (threading, LWPs)**: la vista Threads lista `/proc/<pid>/task/<tid>/*` — para
  el kernel un thread es una "task" más, con su propio `/proc/<pid>/task/<tid>/stat` en
  el mismo formato que `/proc/<pid>/stat`. El Display también usa un thread (no un
  proceso) para leer teclado, siguiendo la excepción explícita de la consigna.

## 5. Limitaciones conocidas

- El Display no puede correr sin una terminal real adjunta al proceso. Dos capas
  distintas de esto, encontradas debuggeando en Windows/Docker Desktop:
  - `multiprocessing` le cierra el `stdin` heredado a **todo** proceso hijo y lo
    reemplaza por `/dev/null` (para que un hijo no compita por leer del teclado del
    padre). Como Display corre como `multiprocessing.Process`, lee del teclado abriendo
    `/dev/tty` directamente en vez de `sys.stdin` (ver sección 3).
  - `docker compose up` trata la salida como logs a seguir (línea por línea, con el
    prefijo `monitor-1 |`), un modelo incompatible con una TUI de pantalla completa que
    repinta por posicionamiento de cursor ANSI en vez de imprimir líneas — el resultado
    es que la pantalla titila sin parar. Probado con `--no-log-prefix`: no lo arregla (el
    problema es el procesamiento línea por línea en sí, no el prefijo). Para usar la TUI
    hace falta `docker compose run --rm monitor` (o `docker run -it`), que conecta la
    terminal directo sin ese procesamiento — mismo código corriendo en ambos casos. Si se
    corre sin terminal real (`up -d`), el Display lo avisa por log y se apaga solo; el
    resto del sistema (Recolector, analizadores, señales, dump) sigue funcionando igual.
- Los logs de `main.py` (confirmaciones de señales recibidas) se imprimen por stdout, que
  es el mismo canal que usa `rich.Live` con `screen=True` para la TUI; pueden pisarse
  visualmente si llega una señal justo mientras la TUI está dibujando.
- El filtro por usuario (`u`) y la columna `usuario` resuelven el UID vía `pwd.getpwuid`
  (lectura de `/etc/passwd`, no de `/proc`); si un proceso corre con un UID que no está en
  `/etc/passwd` del contenedor, se muestra el UID numérico en texto.
- El modo verbose (`SIGUSR2`) hoy sólo togglea un flag y lo loguea; no cambia todavía el
  comportamiento de ningún analizador (ej. mostrar más FDs) — queda como extensión.
- `SIGWINCH` (repintar en resize) no está implementado; `rich.Live` reacciona parcialmente
  solo al redibujar en el próximo ciclo normal.
- Las listas de FDs/threads en la TUI se truncan a las primeras 15 entradas por proceso
  para no romper el layout con procesos que tienen cientos de FDs abiertos.

## 6. Cómo correr y testear

```bash
docker compose up --build
```

Luego, desde otra terminal del host:

```bash
docker ps                                    # ver el nombre del contenedor
docker kill --signal=SIGUSR1 <container>     # genera dump_<timestamp>.json
docker kill --signal=SIGHUP  <container>     # recarga config.json
docker kill --signal=SIGUSR2 <container>     # toggle verbose
docker kill --signal=SIGINT  <container>     # shutdown limpio (o Ctrl+C directo)
```

Para forzar procesos con estados/CPU distintos y ver la TUI reaccionar, se puede abrir un
shell dentro del mismo contenedor y lanzar algo pesado:

```bash
docker compose exec monitor python -c "while True: pass"
```

## 7. Lo que aprendí

Lo más difícil de todo el TP, sin duda, fue algo que ni tenía que ver con escribir código: por qué la pantalla titilaba cuando corría el comando que pide la consigna, docker compose up --build, pero con docker compose run andaba perfecto. Al principio pensé que el error estaba en mi propio código de la TUI. Después de un rato dando vueltas encontramos que multiprocessing le cierra el stdin a los procesos hijos y lo reemplaza por /dev/null, así que el Display nunca podía leer el teclado aunque la terminal estuviera bien. Arreglé eso abriendo /dev/tty a mano, pensé "listo", y la pantalla seguía titilando igual. Probé sacarle el prefijo a los logs pensando que era solo un tema visual y tampoco cambió nada. Al final entendí que el problema no era mío en absoluto: docker compose up está armado para mostrar logs línea por línea, y una TUI de pantalla completa no manda líneas, manda un montón de códigos para mover el cursor y repintar todo el tiempo — son cosas que no combinan. Con docker compose run, que conecta la terminal directo, el mismo código anda perfecto.

Me quedó la sensación de que a veces uno da por sentado que si algo falla es porque programó mal, y no siempre es así. Acá el error estaba en cómo la herramienta interpretaba la salida, no en mi lógica. Tuve que ir descartando cosas una por una hasta llegar ahí, y esa parte de investigar como si fuera un detective terminó siendo lo que más aprendí de toda la entrega.