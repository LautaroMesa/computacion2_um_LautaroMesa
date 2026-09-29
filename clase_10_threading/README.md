# Clase 10 — Threading

Ejercicio obligatorio 9: descargador paralelo con un pool de threads hecho a mano.

## Qué hace

`descargador.py` arma un pool fijo de N threads (`-w`, 4 por defecto). Cada uno
toma URLs de una `queue.Queue` hasta que recibe el centinela `None`; el principal
pone un `None` por worker después de las URLs. Los resultados van a una lista
protegida con `threading.Lock`.

- **Errores de red**: `descargar()` nunca lanza una excepción. Captura `HTTPError`
  (404, 500...), `URLError` (DNS, conexión rechazada, timeout) y `OSError`, y los
  devuelve como resultado fallido. Si una excepción matara al worker, las URLs que
  le tocaban quedarían sin procesar y el pool perdería un thread.
- **La lista de ejemplo trae errores a propósito**: un 404, un dominio inexistente
  (`.invalid` está reservado para eso) y una IP que no responde, para probar el
  timeout. También incluye `httpbin.org/delay/2`, que tarda 2 s.
- **`--secuencial`**: descarga la misma lista de a una URL por vez, para comparar.
- Las duraciones se miden con `time.perf_counter()` y no con `time.time()`. En
  una de las primeras corridas, `time.time()` dio una duración **negativa**
  (-0.31 s) porque el reloj del sistema se ajustó en medio de la medición.
  `perf_counter()` es monotónico y no tiene ese problema.

## Cómo correr

```bash
docker build -t clase10 .
docker run --rm clase10 python descargador.py
docker run --rm clase10 python descargador.py --secuencial
docker run --rm clase10 python descargador.py -w 8 https://example.com https://python.org
```

## Resultados

```
[  W3]  0.02s  https://no-existe.invalid        ERROR URLError: [Errno -2] Name or service not known
[  W0]  0.26s  https://www.python.org              11,505 bytes
[  W2]  0.40s  https://docs.python.org             19,641 bytes
[  W1]  0.52s  https://pypi.org                    27,991 bytes
[  W3]  0.63s  https://httpbin.org/status/404   ERROR HTTP 404
[  W3]  0.76s  https://www.google.com              84,388 bytes
[  W0]  1.23s  https://www.github.com             576,262 bytes
[  W2]  1.97s  https://www.um.edu.ar              152,378 bytes
[  W1]  3.59s  https://httpbin.org/delay/2            327 bytes
[  W3]  5.01s  http://10.255.255.1              ERROR URLError: timed out

Modo: 4 workers
Descargas exitosas: 7/10
Bytes totales: 872,492
Suma de tiempos individuales: 14.40s
Tiempo total: 6.43s
```

Con `--secuencial`, la misma lista tarda **14.94 s**, aproximadamente la suma de
los tiempos individuales. Con 4 workers baja a 6.43 s (**2.3x**). El límite lo pone
la URL que no responde: sola ya ocupa 5 s de timeout, y el total nunca puede bajar
de la descarga más lenta.

**¿Por qué acá sirven los threads si existe el GIL?** Porque la descarga es
I/O-bound. Mientras un thread espera la red (en `recv`, `connect` o DNS), el
intérprete suelta el GIL y los demás siguen trabajando. En la clase 9 el blur era
CPU-bound y hacían falta procesos.

## Checklist de la consigna

- [x] Pool fijo de workers (no un thread por URL)
- [x] Descargas en paralelo
- [x] Errores de red manejados sin crashear (HTTP, DNS, timeout)
- [x] Estadísticas finales
