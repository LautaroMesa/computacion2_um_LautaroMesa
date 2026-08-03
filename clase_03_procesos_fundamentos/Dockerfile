FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends procps psmisc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
