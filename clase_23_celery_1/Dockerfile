# Imagen para correr el worker y los scripts DENTRO de Docker, en la misma red
# que el Redis de docker-compose.yml (ver "Con Docker" en el README).
FROM python:3.11-slim
# celery avisa si corre como root; un usuario comun alcanza
RUN useradd -m celery
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# --chown: encolar.py escribe ultimos_ids.txt en /app
COPY --chown=celery . .
RUN chown celery /app
USER celery
ENV REDIS_URL=redis://redis:6379/0
CMD ["celery", "-A", "tareas", "worker", "--loglevel=info", "--concurrency=2"]
