# Ejercicio 2.1 — Comunicación entre contenedores por nombre

## Cómo correr

```bash
# 1) Red custom (los contenedores conectados a ella se resuelven por nombre)
docker network create ejercicio-red

# 2) Servidor: sirve el contenido de ./sitio (bind mount), en la red custom
docker run -d --name servidor --network ejercicio-red \
  -v "$(pwd)/sitio:/sitio" -w /sitio \
  python:3.11 python -m http.server 8000

# 3) Cliente: pide http://servidor:8000 usando el NOMBRE, no una IP
docker run --rm --network ejercicio-red \
  -v "$(pwd)/cliente.py:/cliente.py" \
  python:3.11 python /cliente.py

# 4) Limpieza
docker rm -f servidor
docker network rm ejercicio-red
```

## Por qué funciona

Los contenedores en una red **default** (bridge por defecto) solo se ven por IP. Una red
**custom** (creada con `docker network create`) trae DNS interno de Docker: cada
contenedor puede resolver a los demás **por su `--name`**, sin necesidad de conocer la
IP (que además puede cambiar entre reinicios). Por eso `cliente.py` apunta a
`http://servidor:8000` directamente por nombre.

El contenido servido (`sitio/index.html`) vive en el host y se monta con `-v`, así que
editarlo desde afuera se refleja al toque en lo que devuelve el servidor.
