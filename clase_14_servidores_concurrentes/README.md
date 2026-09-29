# Clase 14 — Servidores concurrentes

Ejercicio obligatorio 3: los tres descuidos del fork.

## Archivos

| Archivo | Qué es |
|---|---|
| `server_fork.py`, `benchmark.py` | Los de la cátedra, sin cambios (el servidor correcto y el generador de carga) |
| `variantes/server_fork_sin_close_padre.py` | Parte A: el padre no hace `conn.close()` |
| `variantes/server_fork_lista_conexiones.py` | Parte A2: el padre guarda cada `conn` en una lista |
| `variantes/server_fork_sin_sigchld.py` | Parte B: sin handler de `SIGCHLD` |
| `variantes/server_fork_cosecha_simple.py` | Parte C: handler sin `while` (un `waitpid` por señal) |
| `variantes/server_fork_sig_ign.py` | Parte D: `SIGCHLD` en `SIG_IGN` |
| `disparar_60_clientes.py` | 60 clientes que conectan y cortan a la vez: fuerza que 60 hijos del servidor mueran juntos |
| `cosechador_60.py` | El script de la Parte C: 60 hijos que mueren a la vez, con o sin `--bucle` |

## Cómo correr

```bash
docker build -t clase14 .
docker run --rm -it --name fork clase14 bash
python variantes/server_fork_sin_sigchld.py 8080 &
python benchmark.py --clientes 50
ps --ppid $(pgrep -f sin_sigchld) -o pid,stat,comm
python cosechador_60.py; python cosechador_60.py --bucle
```

Todas las mediciones de abajo son en Linux (Ubuntu 24.04 en WSL2, Python 3.12).

---

## Parte A: el padre que no cierra

```
fds padre inicio: 6
fds padre tras benchmark 1: 7
fds padre tras benchmark 2: 7
fds padre tras benchmark 3: 7
```

**1. ¿Crece el número de descriptores?** No. Sube de 6 a 7 y se queda ahí,
aunque pasaron 90 clientes. El único de más es el último `conn`, que sigue
referenciado por la variable.

```
OSError: [Errno 9] Bad file descriptor
```

**2. ¿Quién cerró el descriptor?** CPython. El objeto `socket` solo estaba
referenciado por la variable local `x`. Al volver de `make()`, su contador de
referencias llega a 0, se destruye y su destructor (`socket.__del__` →
`close()`) cierra el fd. El `gc.collect()` ni siquiera hace falta: con conteo de
referencias el cierre es inmediato.

**3.** En el `while True`, `conn` se reasigna en cada `accept()`. El socket de la
vuelta anterior pierde su única referencia, CPython lo destruye y cierra su fd.
Por eso el padre tiene siempre un solo `conn` abierto como máximo.

**4. ¿Entonces el `close()` del padre es innecesario?** No:
- **En C**, `accept()` devuelve un `int`. No hay objeto ni recolector, y nadie lo
  cierra nunca: se filtra un fd por cliente hasta llegar al límite (`ulimit -n`,
  típicamente 1024) y `accept()` empieza a fallar con `EMFILE`.
- **Si el padre guarda las conexiones** (en una lista para estadísticas, un dict
  por cliente, un log), la referencia sobrevive y el fd no se cierra nunca. Es la
  Parte A2.
- **En PyPy** (o cualquier implementación sin conteo de referencias), el objeto
  se destruye recién cuando pasa el GC, que puede tardar mucho. Mientras tanto, los
  fds se acumulan y los clientes no ven el cierre.

**5. Conclusión:** CPython lo cierra por un **detalle de implementación**
(conteo de referencias), no porque el lenguaje lo garantice. El `close()`
explícito expresa la intención ("el padre ya no usa esta conexión") y sigue
siendo correcto si el código cambia (alguien agrega una lista), si se corre en
otro intérprete o si se traduce a C. Un código correcto no puede depender de
cuándo pasa el recolector.

## Parte A2: el cierre que sí se nota

```
fds padre inicio: 6
fds padre tras benchmark 1: 36
fds padre tras benchmark 2: 66
fds padre tras benchmark 3: 96
```

**6.** Ahora sí: **+30 fds por cada benchmark de 30 clientes**, uno por
conexión, y no bajan nunca.

**7. Matar al hijo que atiende a un cliente** (`kill -9` al hijo, con el cliente
bloqueado en `recv()`):

```
con la lista (padre NO cierra):   cliente: recv timeout tras 4s -> NO vio el cierre
con server_fork.py (padre cierra): cliente: recv devolvio b'' (b"" = vio el cierre)
```

Con la lista, el cliente **no se entera**: se queda colgado en `recv()` hasta
su timeout. Con el servidor correcto recibe `b''` al instante.

**8. El mecanismo.** Después de `fork()` hay **dos** descriptores (el del padre y
el del hijo) que apuntan al **mismo** socket del kernel (la misma entrada en la
tabla de archivos abiertos, con un contador de referencias). El kernel cierra la
conexión TCP (manda el FIN) recién cuando se cierra **el último** descriptor. Al
morir el hijo se cierra su copia, pero la del padre sigue viva en la lista, así
que para el kernel la conexión sigue abierta y el cliente no recibe nada. Por eso
el padre tiene que cerrar su copia justo después del `fork()`: así el hijo queda
como único dueño y su cierre (o su muerte) cierra la conexión.

## Parte B: los zombies

```
zombies tras 50 clientes: 50
  PID STAT COMMAND
 2562 Z+   python3
 2564 Z+   python3
 2566 Z+   python3
zombies tras otros 50: 100
```

**4.** Estado `Z` (zombie, `<defunct>`): el hijo terminó, pero el padre nunca hizo
`wait()`, así que el kernel conserva su entrada en la tabla de procesos (PID y
código de salida) para cuando el padre la pida.

**5.** Se acumulan: **50 → 100**. Uno por cliente atendido, y nunca bajan.

**6. Semanas en producción.** Cada zombie ocupa un PID. Con miles de clientes
por hora se llega al límite de PIDs (`/proc/sys/kernel/pid_max`, o el de
`ulimit -u` para el usuario, o el `pids.max` del cgroup en un contenedor), y
`fork()` empieza a fallar con `EAGAIN`: el servidor deja de aceptar clientes, y
otros procesos del mismo usuario tampoco pueden crear hijos. Los zombies no usan
memoria ni CPU, pero agotan los PIDs.

## Parte C: el bucle del cosechador

### Con el servidor y el benchmark

```
zombies (benchmark 50): 14
zombies tras disparar_60 #1: 15
zombies tras disparar_60 #2: 15
zombies tras disparar_60 #3: 15
```

**7.** La guía anticipa cero, pero acá ya con el benchmark de 50 quedaron **14**.
En esta máquina los clientes del benchmark terminan lo bastante juntos como para
que varias `SIGCHLD` se fusionen. **Pero no crecen sin límite** (14 → 15 → 15 →
15): cada señal nueva recoge un hijo cualquiera, a veces uno viejo. Queda una
reserva fija de zombies que no se limpia. No explota como en la Parte B, pero
tampoco está bien.

### Con `cosechador_60.py`

```
sin bucle: hijos=60  recogidos=50  zombies=11
sin bucle: hijos=60  recogidos=43  zombies=18
sin bucle: hijos=60  recogidos=46  zombies=15
sin bucle: hijos=60  recogidos=52  zombies=9
sin bucle: hijos=60  recogidos=48  zombies=13
sin bucle: hijos=60  recogidos=46  zombies=15
con bucle: hijos=60  recogidos=60  zombies=0     (x6, siempre igual)
```

**8. ¿Siempre da lo mismo?** No: entre 9 y 18 zombies según la corrida.

**9. Con el `while True`:** 60 recogidos y 0 zombies en las 6 corridas.

**10. ¿Por qué es intermitente?** Las señales estándar **no se encolan**: el
kernel guarda un solo bit de "SIGCHLD pendiente" por proceso. Si mueren 5 hijos
antes de que el handler llegue a correr, el bit se pone en 1 cinco veces, pero el
handler corre **una vez**. Sin bucle, esa ejecución recoge un hijo y los otros 4
quedan zombies. Cuántas señales se fusionan depende de la temporización exacta
(cuándo el scheduler le da CPU al padre, cuántos hijos mueren en ese intervalo),
por eso cada corrida da distinto. Con el bucle no importa cuántas señales se
fusionaron: cada ejecución vacía todos los hijos terminados.

**11. `WNOHANG`.** Hace que `waitpid` **no bloquee**: si hay un hijo terminado
lo recoge, y si no devuelve `(0, 0)` de inmediato (o lanza `ChildProcessError`
si no quedan hijos). Es lo que permite el bucle "recoger mientras haya". Sin
`WNOHANG`, una vez recogidos los muertos, el `waitpid` siguiente se **bloquea**
esperando que termine algún hijo vivo. Y como está dentro del handler, el servidor
entero se congela (no vuelve al `accept()`) hasta que un cliente se desconecte.

**12. ¿Cómo encontrarlo en producción?** No hay un error ni una excepción:
solo se ve como una cantidad creciente o estable de procesos `<defunct>`. Se
detecta **monitoreando**: `ps -eo stat | grep -c ^Z` o `ps --ppid <pid>` en
una métrica o alerta, el uso de PIDs del cgroup o `/proc/<pid>/status`. Después
hay que reproducirlo con carga concentrada, como `disparar_60_clientes.py`,
porque con carga normal puede no aparecer. Y conviene revisar el código buscando
el patrón: cualquier handler de `SIGCHLD` con un `waitpid` que no esté en un bucle
es sospechoso.

## Parte D: la alternativa

```
zombies con SIG_IGN tras 230 clientes: 0
```

**¿Siguen apareciendo zombies?** No, cero después de 230 clientes (benchmark +
3 ráfagas de 60). **¿Quién los recoge?** El **kernel**. En Linux (y por POSIX),
poner explícitamente la disposición de `SIGCHLD` en `SIG_IGN` le indica al kernel
que el padre no va a pedir el estado de sus hijos, así que al terminar se liberan
directamente, sin pasar por el estado zombie. Esto **no** es lo mismo que no
registrar ningún handler (Parte B): la disposición por defecto (`SIG_DFL`)
también ignora la señal, pero sin activar esta liberación automática.

La contra es que el padre ya no puede saber con qué código terminó cada hijo:
`waitpid` falla con `ChildProcessError`.

## Checklist de la consigna

- [x] Descriptores del padre que crecen si no cierra (A2: 6 → 36 → 66 → 96)
- [x] Por qué el cliente no ve el cierre (dos descriptores al mismo socket; el FIN sale con el último)
- [x] Zombies acumulándose sin handler (50 → 100)
- [x] Cosechador sin bucle que deja zombies bajo carga (9 a 18 de 60; con bucle, 0)
- [x] Qué hace `WNOHANG` y por qué hace falta
- [x] `SIG_IGN` funciona (0 zombies) y quién cosecha (el kernel)
