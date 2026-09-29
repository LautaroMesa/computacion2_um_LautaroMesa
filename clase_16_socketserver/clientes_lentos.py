#!/usr/bin/env python3
"""Conecta N clientes a la vez, cada uno manda una linea y espera la
respuesta. Mide el tiempo total: si el servidor atiende en paralelo, tarda
lo que tarda UN cliente; si atiende de a uno, N veces eso.

Uso:
    python3 clientes_lentos.py [puerto] [N]
"""
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor

PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
N = int(sys.argv[2]) if len(sys.argv) > 2 else 2


def cliente(i):
    inicio = time.perf_counter()
    with socket.create_connection(('localhost', PUERTO), timeout=30) as s:
        s.sendall(b'cliente %d\n' % i)
        respuesta = s.makefile('rb').readline()
    return i, respuesta.strip(), time.perf_counter() - inicio


if __name__ == '__main__':
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N) as pool:
        for i, resp, t in pool.map(cliente, range(N)):
            print(f'  cliente {i}: {resp!r} en {t:.2f}s')
    print(f'Total para {N} clientes: {time.perf_counter() - inicio:.2f}s')
