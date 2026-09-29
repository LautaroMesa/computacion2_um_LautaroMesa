# Clase 8 — Multiprocessing: fundamentos

Esta clase no tiene ejercicio obligatorio; están resueltos los 5 de la guía.

| Archivo | Ejercicio |
|---|---|
| `ej1_primer_process.py` | El mismo padre/hijo con `os.fork()` y con `Process` |
| `ej2_cinco_workers.py` | 5 procesos con espera aleatoria; tiempo total ≈ el del más lento |
| `ej3_productor_consumidor.py` | Productor/consumidor con `multiprocessing.Queue` y centinela `None` |
| `ej4_ping_pong.py` | 5 mensajes ida y vuelta por `Pipe()` |
| `ej5_fork_vs_spawn.py` | Tiempo de crear 100 procesos con cada método de arranque |

## Cómo correr

```bash
docker build -t clase8 .
docker run --rm clase8 python ej1_primer_process.py      # (idem el resto)
docker run --rm clase8 python ej5_fork_vs_spawn.py 200   # N opcional
```

## Ejercicio 1: ¿qué pasos te ahorrás con `Process`?

| `os.fork()` | `multiprocessing.Process` |
|---|---|
| `if pid == 0:` para separar hijo y padre | Pasás la función en `target=` |
| El hijo tiene que llamar a `os._exit()`; si no, sigue ejecutando el código del padre | El hijo termina solo al volver de la función |
| `os.waitpid()` + `waitstatus_to_exitcode()` | `join()` y `exitcode` |
| Solo Unix | Unix y Windows (con `spawn`) |

Una trampa que apareció al probarlo: `os._exit()` sale **sin vaciar el buffer
de stdout**. Si la salida va a un archivo o pipe (por ejemplo `docker logs` o
`| cat`), el `print` del hijo se pierde. Por eso ese print lleva `flush=True`.

## Ejercicio 2

```
worker 0 termino (0.54s)
worker 1 termino (0.90s)
worker 2 termino (1.25s)
worker 4 termino (1.27s)
worker 3 termino (1.68s)

Tiempo total:            1.70s
Mas lento:               1.68s
Suma (si fuera en serie): 5.64s
```

## Ejercicio 4

```
  hijo  recibio: ping 1
padre recibio: pong 1
  hijo  recibio: ping 2
padre recibio: pong 2
...
```

El padre cierra su copia de `extremo_hijo` apenas arranca el hijo, igual que
con los pipes de la clase 5.

## Ejercicio 5: fork vs spawn (Linux, 100 procesos)

```
      fork: 0.106s para 100 procesos  (1.1 ms c/u)
     spawn: 1.116s para 100 procesos  (11.2 ms c/u)
forkserver: 0.406s para 100 procesos  (4.1 ms c/u)
```

- **fork** copia el proceso padre (con copy-on-write), así que el hijo arranca con el
  intérprete ya cargado. Es el más rápido.
- **spawn** arranca un intérprete de Python nuevo desde cero, que tiene que
  importar el módulo principal y deserializar el `target`. Es unas 10 veces más
  lento, pero es el único que existe en Windows (y el default en macOS), y el
  hijo no hereda locks tomados ni threads del padre.
- **forkserver** es un punto medio: un servidor limpio que se forkea a pedido.

Uso `get_context(metodo)` en lugar de `set_start_method()` porque este último
solo se puede llamar una vez por programa, y así mido los tres en la misma corrida.
