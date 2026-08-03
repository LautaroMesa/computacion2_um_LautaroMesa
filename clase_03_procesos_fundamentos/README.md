# Clase 3 — Procesos: Fundamentos

Ejercicios obligatorios 1 a 4 (según `ejercicios.md` del repo del profe).

## Cómo correr

```bash
docker build -t clase3 .
docker run --rm clase3 python ejercicio1_explorar_proceso.py
docker run --rm clase3 python ejercicio2_arbol_procesos.py
docker run --rm clase3 python ejercicio3_memoria_virtual.py
docker run --rm clase3 python ejercicio4_pid_reciclado.py
```

## Ejercicio 1 — Explorar tu propio proceso

Lee `/proc/<pid>` del propio script: PID, PPID, cwd, file descriptors abiertos y
las primeras líneas de `maps`.

## Ejercicio 2 — Árbol de procesos

Corre `pstree -p`, `ps -ef --forest` y `ps -o pid,ppid,comm`, y arma el linaje del
proceso subiendo por `PPid` (de `/proc/<pid>/status`) hasta llegar a PID 1.

**Quién es PID 1**: el primer proceso que crea el kernel al arrancar (init/systemd en un
Linux normal; dentro de un contenedor Docker, el proceso que el propio `docker run`
lanza como comando principal — acá, `python ejercicio2_arbol_procesos.py`). Todo proceso
huérfano termina siendo adoptado por PID 1.

## Ejercicio 3 — Memoria virtual

Lanza un proceso Python de fondo (`time.sleep(60)`) e inspecciona su
`/proc/<pid>/maps`, identificando el segmento de texto (ejecutable, permisos `r-xp`),
`[heap]`, `[stack]` y las librerías compartidas cargadas.

## Ejercicio 4 — PIDs y reciclado

Lanza 20 procesos seguidos (`sh -c 'echo "PID=$$"'`) y muestra `pid_max` del sistema.
Con solo 20 no se ve el reciclado en vivo (pid_max suele ser >4 millones), pero el
script deja explicado el mecanismo: el kernel asigna el siguiente PID libre, y al llegar
al máximo vuelve a buscar desde abajo, en vez de crecer indefinidamente.
