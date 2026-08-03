# Ejercicio 4 — Docker Compose: app + Redis

`app.py` se conecta a Redis por el hostname `redis` (resuelto por la red que arma Compose
automáticamente para todos los servicios del mismo archivo) e incrementa un contador.

## 4.1 — Levantar y verificar

```bash
docker compose up --build
docker compose ps
docker compose logs redis
```

`app` corre una vez, imprime el contador, y termina (no es un servidor); `redis` queda
corriendo. Cada `docker compose up` vuelve a correr `app`, así que el contador sigue
subiendo... **mientras Redis no se reinicie sin persistencia**.

## 4.2 — Persistencia

Este `docker-compose.yml` YA tiene la persistencia puesta (`redis-data:/data` +
`--appendonly yes`, que le dice a Redis que escriba cada cambio a disco en vez de
guardar todo solo en memoria). Para ver la diferencia con/sin persistencia:

```bash
# Con persistencia (tal cual esta el archivo): el contador sigue donde quedo
docker compose up --build     # contador: 1
docker compose down           # NO borra el volumen redis-data
docker compose up             # contador: 2 (sigue de donde quedo)

# Sin persistencia: comentar las lineas de "command" y "volumes: redis-data:/data"
# del servicio redis, y correr:
docker compose down -v        # -v SI borra los volúmenes con nombre
docker compose up --build     # contador: 1 otra vez (Redis arranco en blanco)
```

## 4.3 — Hot reload

El volumen `.:/app` en el servicio `app` monta el código fuente del host directo adentro
del contenedor, así que **no hace falta reconstruir la imagen** para que un cambio en
`app.py` se vea reflejado:

```bash
# Cambiar algo en app.py (ej: el mensaje del print)
docker compose run --rm app    # corre con el codigo actualizado, SIN docker compose build
```
