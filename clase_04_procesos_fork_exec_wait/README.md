# Clase 4 — Procesos: fork, exec, wait

Ejercicio obligatorio 5: mini-shell.

## Qué hace

Un loop `while True` que muestra `$ `, lee un comando y:
- `exit` → termina el shell.
- `cd [dir]` → cambia de directorio **sin fork** (tiene que afectar al propio proceso
  del shell; un hijo con `fork()` cambiaría su propio cwd, no el del padre).
- cualquier otro comando → patrón `fork()` + `execvp()` + `wait()`: el hijo se
  reemplaza a sí mismo por el comando (`execvp`), el padre espera a que termine y
  muestra el código de salida si fue distinto de 0.

## Cómo correr

```bash
docker build -t clase4 .
docker run --rm -it clase4 python minishell.py
```

Ejemplo de sesión:

```
$ ls
$ pwd
$ cd /tmp
$ pwd
$ echo hola
$ exit
```
