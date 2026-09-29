# Clase 18 — De yield a asyncio

Ejercicio obligatorio 2: construir el scheduler.

## Qué hay

`mi_scheduler.py` es un event loop cooperativo escrito desde cero con
generadores, en dos versiones:

- **`scheduler(tareas)`**: round-robin con una `deque`. Saca una tarea, la
  reanuda con `next()` hasta su próximo `yield` y, si no terminó
  (`StopIteration`), la manda al final de la cola. Cuenta los `next()`.
- **`scheduler_con_tiempo(tareas)`**: las tareas ceden con `yield from
  dormir(s)`, que entrega la hora a la que quieren volver. El scheduler las guarda
  en un **heap ordenado por hora de despertar** y, si ninguna está lista, **duerme
  hasta la próxima** en lugar de girar preguntando.

```bash
python3 mi_scheduler.py intercalado      # Parte A
python3 mi_scheduler.py sin-yield        # Parte A.3
python3 mi_scheduler.py egoista          # Parte B
python3 mi_scheduler.py tiempo 3         # Parte C, 3 corridas
python3 mi_scheduler.py sin-yield-from   # Parte D
```

Con Docker: `docker build -t clase18 . && docker run --rm clase18 python mi_scheduler.py tiempo 3`.
No usa nada fuera de la biblioteca estándar.

---

## Parte A: el intercalado

**1.** Tres tareas: A (3 pasos), B (1 paso) y C (5 pasos):

```
[A] paso 1/3
[B] paso 1/1
[C] paso 1/5
[A] paso 2/3
[B] terminada
[C] paso 2/5
[A] paso 3/3
[C] paso 3/5
[A] terminada
[C] paso 4/5
[C] paso 5/5
[C] terminada
next() en total: 12
```

Salen **intercaladas por turnos**: un paso de cada una, en orden A, B, C, y a
medida que terminan (primero B, después A) quedan las demás. Cada `yield` es el
punto donde la tarea le devuelve el control al scheduler.

**2.** **12** `next()`: uno por paso (3 + 1 + 5 = 9) y **uno más por tarea**, el
que la reanuda después de su último `yield`. Ese `next()` ejecuta el código final
(el print de "terminada") y recibe `StopIteration`.

**3. Una tarea sin ningún `yield`:** hay dos casos.
- Si la función **no tiene `yield` en ningún lado**, no es un generador: al
  llamarla se ejecuta **entera en ese momento** (antes de que el scheduler
  arranque) y devuelve `None`, y `next(None)` da `TypeError`.
- Si tiene un `yield` inalcanzable (como `tarea_sin_yield` en mi código, con un
  `return` antes), es un generador, pero el primer `next()` corre todo el cuerpo
  de una vez y lanza `StopIteration`:

```
[A] paso 1/2
[S] hago todo de una
[B] paso 1/2
...
next() en total: 7
```

En los dos casos, la tarea hace todo su trabajo **sin ceder nunca**. Si es corta,
no pasa nada; si es larga, es el problema de la Parte B.

## Parte B: la cooperación es obligatoria

**4.** Con `tarea_egoista` (un `time.sleep(3)` sin ceder) entre A y B:

```
 0.00s [A] paso 1/3
 0.00s [EGO] me pongo a calcular
 3.00s [EGO] listo
 3.00s [B] paso 1/3
 3.00s [A] paso 2/3
 ...
Total: 3.00s
```

Durante esos 3 segundos **nadie más avanza**: A y B quedan congeladas. B ni
siquiera arranca hasta el segundo 3. El scheduler está atrapado en el `next()` de
la egoísta y no puede hacer nada hasta que esa tarea le devuelva el control.

**5. ¿Con threads habría pasado lo mismo?** No. Con threads (clase 10), el que
decide cuándo cambiar de tarea es el **sistema operativo** (y en Python, además,
el intérprete suelta el GIL cada ~5 ms y en cada operación bloqueante como
`sleep`). Un thread que duerme o calcula no impide que los demás corran.

- **Preventiva** (threads, procesos): el scheduler del SO **le quita** la CPU
  a una tarea cuando quiere (por timer), sin pedirle permiso. Ninguna tarea
  puede acaparar todo, pero cualquier instrucción puede ser interrumpida, y por
  eso hacen falta locks (clase 11).
- **Cooperativa** (generadores, asyncio): cada tarea **entrega** el control
  voluntariamente en puntos explícitos (`yield`, `await`). Entre dos de esos
  puntos, la tarea corre sin que nadie la interrumpa, lo que simplifica mucho la
  sincronización. La contra es que una sola tarea que no coopera frena a todas.

**6. La regla:** *nunca bloquear el event loop*. Toda operación lenta (I/O,
`sleep`) tiene que **ceder** (`await asyncio.sleep`, sockets no bloqueantes), y
el trabajo de CPU largo se manda a otro thread o proceso
(`run_in_executor`). Es lo mismo que en la clase 17: un servidor con `select` y un
solo hilo atiende a miles de clientes **solo si cada handler hace poco y vuelve
enseguida al bucle**. Un handler que bloquea congela a todos los clientes.

## Parte C: agregar tiempo

**7.** `dormir()`:

```python
def dormir(segundos):
    yield time.monotonic() + segundos
```

No duerme: **cede** entregando al scheduler la hora a la que quiere volver.
El scheduler la guarda en el heap y no la vuelve a reanudar antes de esa hora.

**8. ¿Por qué no puede usar `time.sleep()`?** Porque `time.sleep()` bloquea **el
hilo**, y en un scheduler cooperativo hay un solo hilo para todas las tareas: sería
la tarea egoísta de la Parte B. La idea es que **la tarea no espere**: le avisa al
scheduler cuándo despertarla, y mientras tanto el scheduler reanuda a otras. El
único que puede dormir es el scheduler, y solo cuando **ninguna** tarea tiene nada
que hacer.

**9.** Tres tareas que esperan 0,15 s tres veces cada una (tres corridas):

```
Total: 0.469s  (suma de esperas: 9 x 0.15 = 1.35s; next(): 12; el scheduler durmio 0.469s)
Total: 0.469s  (... el scheduler durmio 0.463s)
Total: 0.469s  (... el scheduler durmio 0.469s)
```

**Mucho menos que la suma**: 0,47 s contra 1,35 s. Las esperas **se solapan**:
las tres tareas duermen al mismo tiempo, así que el total es el de **una**
tarea (3 × 0,15 = 0,45 s) y no el de las tres. La diferencia de ~0,02 s es la
granularidad del `sleep` del sistema (medido en Windows, donde el timer tiene
una resolución de ~15 ms).

### Mi scheduler contra `scheduler.py` de la cátedra

El `scheduler_con_tiempo` de la cátedra, cuando ninguna tarea está lista, vuelve
a meterla en la cola y sigue girando: hace **espera activa**. El mío duerme hasta
la próxima hora de despertar. Medido con `time.process_time()`:

```
profe (recorre la cola)    reloj 0.469s   CPU 0.469s
mio (heap + sleep)         reloj 0.468s   CPU 0.000s
```

Los dos tardan lo mismo, pero el de la cátedra usa **100% de un núcleo** para
esperar. Es lo que hace el event loop real de asyncio: calcula cuánto falta para
el próximo timer y lo pasa como timeout a `select`/`epoll` (clase 17), así que el
proceso duerme en el kernel hasta que haya un evento de I/O o se cumpla el timer.

## Parte D: yield from

**10. ¿Qué hace `yield from dormir(espera)`?** **Delega** en el sub-generador:
cada valor que `dormir()` produce con `yield` sube directo hasta el que llamó
a `next()` en la tarea, que es el scheduler. Cuando `dormir()` termina,
`yield from` devuelve su valor de retorno y la tarea sigue. Para el scheduler es
como si el `yield` estuviera escrito dentro de `tarea_lenta`.

Llamar a `dormir(espera)` a secas **no ejecuta nada**: llamar a una función
generadora solo **crea** el objeto generador, sin correr ni una línea de su
cuerpo. Hay que iterarlo para que avance, y `yield from` es lo que lo itera y
conecta sus `yield` con el scheduler.

**11.** Sin el `yield from`:

```
0.00s [A] 1/3
0.00s [A] 2/3
0.00s [A] 3/3
0.00s [A] terminada
0.00s [B] 1/3
...
Total: 0.000s  (deberia ser ~0.45s si durmiera)
```

**No duerme nada** y ni siquiera intercala: A hace sus tres pasos de corrido y
recién después B, porque la tarea nunca cede. Cada `dormir(espera)` crea un
generador que se tira sin usar.

**No falla ruidosamente** porque crear un generador y descartarlo es
perfectamente válido en Python: no hay ninguna excepción, solo un objeto que el
recolector libera. Es el mismo error que olvidar el `await` en asyncio
(`asyncio.sleep(1)` sin `await`), donde crear la corrutina tampoco la ejecuta.
Ahí Python al menos avisa con un `RuntimeWarning: coroutine ... was never
awaited`; con generadores no hay ni advertencia.

## Checklist de la consigna

- [x] Scheduler que intercala tareas, escrito por mí
- [x] Contador de reanudaciones (12 = 9 pasos + 3 finales)
- [x] Tarea que no cede probada y explicada (congela a todas 3 s)
- [x] Diferencia entre concurrencia cooperativa y preventiva
- [x] `dormir()` que cede el control, sin `time.sleep()` en la tarea
- [x] Esperas que se solapan (0,47 s contra 1,35 s de suma)
- [x] Qué hace `yield from` y qué pasa si se omite
