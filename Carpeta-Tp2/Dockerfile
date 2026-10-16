FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app
COPY scripts/ ./scripts

# Corre como root a proposito: ./estado se monta desde el host, y en un host
# Linux ese directorio lo crea Docker a nombre de root. Con un usuario sin
# privilegios, el volcado del apagado fallaria por permisos.
RUN mkdir -p /app/estado

ENV TP2_HOST=0.0.0.0 \
    TP2_PUERTO=8000 \
    TP2_DIR_ESTADO=/app/estado \
    PYTHONUNBUFFERED=1
EXPOSE 8000

# Forma "exec" (lista): python es el PID 1 y recibe el SIGTERM de
# `docker compose stop` directamente, sin un shell en el medio que se lo coma.
CMD ["python", "-m", "app.main"]
