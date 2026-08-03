import redis

# "redis" es el --name del contenedor de Redis en la red custom: se resuelve
# por DNS interno de Docker, igual que "servidor" en el ejercicio 2.1.
r = redis.Redis(host='redis', port=6379, decode_responses=True)

print('SET saludo "hola desde python"')
r.set('saludo', 'hola desde python')

print('GET saludo ->', r.get('saludo'))

print('INCR contador (x3)')
for _ in range(3):
    valor = r.incr('contador')
print('contador ->', valor)

print('\nTodas las claves guardadas:', r.keys('*'))
