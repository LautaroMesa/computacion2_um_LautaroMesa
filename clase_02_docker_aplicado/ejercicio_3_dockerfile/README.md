# Ejercicio 3 — Imagen propia (`mi-cowsay`)

## 3.1 — Build y prueba

```bash
docker build -t mi-cowsay .
docker run --rm mi-cowsay                  # mensaje default
docker run --rm mi-cowsay Hola profe       # mensaje custom
```

Nota: el Dockerfile usa `ENTRYPOINT ["python", "app.py"]`, no `CMD`. Con `CMD`, los
argumentos que le pasás a `docker run` **reemplazan** el comando entero (`docker run
mi-cowsay Hola profe` intentaría ejecutar un programa llamado `Hola`, y fallaría). Con
`ENTRYPOINT`, esos argumentos se **agregan** al final del comando fijo — que es lo que
hace falta para pasarle el mensaje custom a `app.py`.

## 3.2 — Inspeccionar capas

```bash
docker history mi-cowsay
docker images | grep -E "mi-cowsay|python.*3.11-slim"
```

`docker history` muestra una capa por cada instrucción del Dockerfile (`FROM`,
`WORKDIR`, `COPY requirements.txt`, `RUN pip install...`, `COPY app.py`, `CMD`).
Comparando el tamaño de `mi-cowsay` contra `python:3.11-slim` (la base), la diferencia
es lo que agregaron nuestras propias capas — en este caso, casi nada, porque `app.py`
pesa unos pocos KB y no instalamos ninguna dependencia externa.

## 3.3 — Cache al reconstruir

```bash
# 1) Tocar solo app.py y reconstruir
echo "# comentario" >> app.py
docker build -t mi-cowsay .
# -> "COPY requirements.txt ." y "RUN pip install..." salen CACHED:
#    Docker compara el contenido de requirements.txt (no cambió) y reusa la capa.
#    Solo se re-ejecuta "COPY app.py ." en adelante.

# 2) Tocar requirements.txt y reconstruir
echo "colorama" >> requirements.txt
docker build -t mi-cowsay .
# -> "RUN pip install..." YA NO sale cached: cambio el contenido de la capa
#    anterior (COPY requirements.txt), asi que TODO lo que viene despues
#    se invalida y se re-ejecuta, aunque app.py no haya cambiado de nuevo.
```

**Por qué pasa esto**: Docker construye la imagen como una pila de capas, una por
instrucción, y cachea cada una por el hash de su contenido + el hash de la capa
anterior. Si una capa cambia, **todas las que vienen después en el Dockerfile se
invalidan**, aunque su propio contenido no haya cambiado — por eso el orden importa:
poner `COPY requirements.txt` + `pip install` ANTES de `COPY app.py` (en vez de copiar
todo junto) es a propósito, para que cambiar el código de la app no obligue a
reinstalar dependencias cada vez.
