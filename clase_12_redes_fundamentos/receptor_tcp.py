#!/usr/bin/env python3
"""Receptor TCP que muestra CADA recv() por separado.

Es la version "con lupa" de `nc -l 8080 | od -c`: od junta todo lo que
llega y no deja ver cuantas lecturas hizo el receptor. Aca cada recv() se
imprime en su propia linea, asi se ve si tres send() llegaron en uno, dos
o tres pedazos.

Uso:
    python3 receptor_tcp.py [puerto]
"""
import socket
import sys

PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('localhost', PUERTO))
    srv.listen(1)
    conn, origen = srv.accept()
    with conn:
        n = 0
        while True:
            datos = conn.recv(4096)
            if not datos:          # b'' = el otro lado cerro
                break
            n += 1
            print(f"recv #{n}: {datos!r}")
        print(f"TCP: {n} recv() con datos")
