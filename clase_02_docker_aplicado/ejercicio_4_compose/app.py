import os
import time

import redis

HOST = os.environ.get('REDIS_HOST', 'localhost')

# depends_on de compose solo espera a que el CONTENEDOR de redis arranque,
# no a que redis ya este aceptando conexiones. Reintentamos un poco en vez
# de asumir que ya esta listo.
r = None
for intento in range(10):
    try:
        candidato = redis.Redis(host=HOST, port=6379, decode_responses=True)
        candidato.ping()
        r = candidato
        break
    except redis.ConnectionError:
        print(f'Esperando a Redis... (intento {intento + 1})')
        time.sleep(1)

if r is None:
    raise SystemExit('No se pudo conectar a Redis')

contador = r.incr('contador')
print(f'Contador: {contador}')
