# Clase 5 — Pipes y redirección

Ejercicio obligatorio 5: extender el mini-shell de la Clase 4 para soportar
redirección de salida (`>`) y, como bonus, entrada (`<`).

## Qué hace

`parsear_linea()` separa comando/args de los operadores `>`/`<` (usando `shlex` para
respetar comillas). `ejecutar()` hace `fork()`; en el hijo, ANTES de `execvp()`, abre el
archivo correspondiente y usa `os.dup2()` para redirigir el fd 0 (stdin) o 1 (stdout) —
como `exec` no toca la tabla de file descriptors, el comando que arranca después hereda
esa redirección sin saber que existe.

## Cómo correr

```bash
docker build -t clase5 .
docker run --rm -it clase5 python minishell_redireccion.py
```

## Tests de verificación (los que pide la consigna)

```
minish$ echo "hola mundo" > test.txt
minish$ cat test.txt
hola mundo

minish$ ls -la > listado.txt
minish$ wc -l < listado.txt
(cantidad de líneas)

minish$ exit
```

## Limitación conocida

El parser reconoce `>` y `<` como tokens sueltos (separados por espacios de lo demás).
Si se escriben pegados al nombre del archivo sin espacio (`ls>out.txt`), `shlex` los
trata como parte de un mismo token y no se detectan — no es un caso que pidan los tests
de verificación, pero es una limitación real del parser tal como está.
