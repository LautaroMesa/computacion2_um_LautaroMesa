#!/usr/bin/env python3
"""Conecta 60 clientes en paralelo y los desconecta casi al instante, para
que del lado del servidor 60 hijos terminen casi simultaneamente. El punto
es forzar que lleguen muchas señales SIGCHLD "pisadas" entre si (el kernel
no las encola), justo el escenario que rompe un handler sin loop.
"""
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

HOST = 'localhost'
PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
N = int(sys.argv[2]) if len(sys.argv) > 2 else 60


def cliente(_):
    try:
        with socket.create_connection((HOST, PUERTO), timeout=5):
            pass  # conecta y cierra ya: el hijo del server termina rapido
    except OSError as e:
        print(f'error: {e}')


def main():
    with ThreadPoolExecutor(max_workers=N) as pool:
        list(pool.map(cliente, range(N)))
    print(f'{N} clientes conectados y desconectados')


if __name__ == '__main__':
    main()
