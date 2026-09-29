FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# dentro del contenedor hay que escuchar en todas las interfaces, no en 127.0.0.1
ENV HOST=0.0.0.0
EXPOSE 8000
CMD ["python", "api.py"]
