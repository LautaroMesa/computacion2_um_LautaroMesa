# Ejercicio 2.2 — Redis desde Python

## Cómo correr

```bash
docker network create ejercicio-red   # si no existe todavia (ver ejercicio 2.1)

# Redis en la red custom
docker run -d --name redis --network ejercicio-red redis:7-alpine

# Cliente Python: instala el paquete "redis" y corre la demo
docker run --rm --network ejercicio-red \
  -v "$(pwd):/app" -w /app \
  python:3.11-slim sh -c "pip install --no-cache-dir -r requirements.txt && python redis_demo.py"

# Limpieza
docker rm -f redis
docker network rm ejercicio-red
```

## ¿La info persiste?

Mientras el contenedor de Redis siga corriendo, sí — Redis guarda todo en memoria y
sirve cualquier cliente que se conecte a él. Pero si el contenedor se **detiene y se
borra** (`docker rm`), esa memoria se pierde entera: por defecto Redis no escribe nada a
disco. Para que sobreviva a un restart hace falta persistencia explícita (volumen +
`--appendonly yes`), que es justo lo que se agrega en el ejercicio 4.2.
