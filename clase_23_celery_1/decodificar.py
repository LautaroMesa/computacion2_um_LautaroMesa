#!/usr/bin/env python3
"""Parte B: mirar el mensaje crudo que Celery deja en la lista 'celery' de Redis.

Lee el primer mensaje de la cola SIN sacarlo (LINDEX, no LPOP), decodifica
el body de base64 y muestra qué viaja: headers y argumentos. Si buscás el
código de la función, no lo vas a encontrar.

Uso (con el broker arriba y SIN worker, para que haya algo en la cola):
    python3 encolar.py
    python3 decodificar.py
"""
import base64
import json
import sys

import redis   # viene con celery[redis]

from tareas import REDIS_URL

r = redis.Redis.from_url(REDIS_URL)
crudo = r.lindex('celery', 0)
if crudo is None:
    sys.exit('La cola está vacía: encolá algo sin ningún worker corriendo.')

mensaje = json.loads(crudo)
print(f'LLEN celery = {r.llen("celery")}   ({len(crudo)} bytes el primer mensaje)\n')

print('Envoltorio (lo que ve Redis):')
for clave in ('content-type', 'content-encoding', 'properties'):
    valor = mensaje[clave]
    if clave == 'properties':
        valor = {k: valor[k] for k in ('body_encoding', 'delivery_info')}
    print(f'  {clave:<17} {valor}')

print('\nHeaders (para el worker):')
for clave in ('task', 'id', 'argsrepr', 'kwargsrepr', 'origin', 'retries', 'eta'):
    print(f'  {clave:<11} {mensaje["headers"].get(clave)!r}')

cuerpo = base64.b64decode(mensaje['body'])
print(f'\nbody en base64: {mensaje["body"]}')
print(f'body decodificado: {cuerpo.decode()}')
args, kwargs, opciones = json.loads(cuerpo)
print(f'  args={args}  kwargs={kwargs}  callbacks={opciones.get("callbacks")}')

print('\n¿Está el código de la función en el mensaje?',
      'SÍ' if b'def ' in crudo or b'time.sleep' in crudo else
      'NO: solo viaja el nombre "tareas.sumar" y los argumentos.')
