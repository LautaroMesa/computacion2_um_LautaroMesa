# Clase 11 — Sincronización

Ejercicio obligatorio 5: lock de lectores/escritores.

## Archivos

| Archivo | Qué hace |
|---|---|
| `rwlock.py` | `ReadWriteLock` con dos `Condition` sobre un mismo `Lock`, más los context managers `ReadLock` y `WriteLock` |
| `readers_writers.py` | Test de la consigna (5 lectores y 2 escritores) con un monitor que **verifica** las reglas |
| `demo_starvation.py` | Mide cuánto espera un escritor con preferencia a lectores y con preferencia a escritores |

## Cómo correr

```bash
docker build -t clase11 .
docker run --rm clase11 python readers_writers.py
docker run --rm clase11 python demo_starvation.py
```

## El cambio respecto del esqueleto: preferencia a escritores

En el esqueleto de la consigna, un lector solo espera si hay un escritor
**escribiendo**. Si los lectores se superponen todo el tiempo (siempre entra uno
nuevo antes de que salga el último), `readers` nunca llega a 0 y el escritor
espera indefinidamente. Eso es **starvation**, y la consigna pide evitarla.

La solución es contar también a los escritores **esperando** (`writers_waiting`).
Si hay alguno, los lectores nuevos se quedan afuera: los que ya estaban terminan
y el escritor entra. `demo_starvation.py` lo mide con 8 lectores leyendo sin
parar y un escritor que pide el lock a los 0,5 s:

```
8 lectores leyendo sin parar durante 3.0s; un escritor pide el lock a los 0.5s

  preferencia a lectores     el escritor espero 2.522s
  preferencia a escritores   el escritor espero 0.019s
```

Con preferencia a lectores, el escritor recién entra cuando los lectores dejan
de leer (al final de la prueba). Con preferencia a escritores entra apenas
terminan los lectores que ya estaban adentro.

**Contra**: con escritores que llegan todo el tiempo, ahora son los *lectores*
los que pueden quedar esperando. Una solución totalmente justa requiere una
cola FIFO de turnos. Para este caso (lecturas frecuentes y escrituras
ocasionales), preferir a los escritores es lo razonable. Por ejemplo,
`sync.RWMutex` de Go hace exactamente esto: con un `Lock()` pendiente, los
`RLock()` nuevos esperan.

### Otros detalles

- **`while` y no `if` antes de cada `wait()`**: entre el `notify()` y el momento
  en que el hilo despierta, otro hilo pudo tomar el lock y cambiar el estado.
  Además existen los *spurious wakeups*. Por eso siempre se vuelve a chequear la condición.
- **`notify_all()` a los lectores y `notify()` a los escritores**: los lectores
  pueden entrar todos juntos, mientras que de los escritores solo puede pasar uno.
- **El contador `datos["lecturas"] += 1` del test original tenía una race**:
  varios lectores están adentro al mismo tiempo, y `+=` no es atómico. El
  read lock permite concurrencia entre lectores, así que no protege ese contador.
  En mi versión va bajo un lock aparte.

## Verificación

`readers_writers.py` lleva un monitor que registra cuántos lectores y escritores
hay adentro en cada momento y anota cualquier violación de las reglas:

```
[Lector 2] Leyo valor=0  (lectores adentro: 1)
[Lector 0] Leyo valor=0  (lectores adentro: 2)
[Lector 4] Leyo valor=0  (lectores adentro: 3)
[Lector 1] Leyo valor=0  (lectores adentro: 4)
[Lector 3] Leyo valor=0  (lectores adentro: 5)
[Escritor 0] Escribio valor=0
[Escritor 1] Escribio valor=100
[Lector 3] Leyo valor=100  (lectores adentro: 1)
...
Estadisticas finales:
  Valor final: 102
  Total lecturas: 25 (esperadas 25)
  Total escrituras: 6 (esperadas 6)
  Maximo de lectores simultaneos: 5
  Maximo de escritores simultaneos: 1
  Violaciones de las reglas: ninguna
```

En 10 corridas seguidas, siempre dio 5 lectores simultáneos como máximo, 1
escritor como máximo y ninguna violación.

Se ve la preferencia a escritores: cuando los dos escritores piden el lock,
escriben uno detrás del otro antes de que vuelvan a entrar los lectores.

## Checklist de la consigna

- [x] Múltiples lectores simultáneos (hasta 5 verificado)
- [x] Escritores bloqueados mientras hay lectores
- [x] Lectores bloqueados mientras hay escritor
- [x] Un solo escritor a la vez
- [x] Espera con `Condition`
- [x] Context managers
- [x] Sin deadlocks y sin starvation del escritor (medido)
