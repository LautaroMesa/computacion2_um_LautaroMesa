#!/usr/bin/env python3
"""Variante Parte D: SIGCHLD puesto en SIG_IGN en vez de un handler propio.

Segun POSIX, poner la disposicion de SIGCHLD explicitamente en SIG_IGN le
dice al kernel que cosecheautomaticamente a los hijos terminados (no es lo
mismo que "no registrar ningun handler": eso deja la disposicion default,
que NO activa este comportamiento especial).
"""
import os
import signal
import socket
import sys
import time

HOST = '0.0.0.0'
PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080
LENTO = float(sys.argv[sys.argv.index('--lento') + 1]) if '--lento' in sys.argv else 0.0


def atender(conn):
    if LENTO:
        time.sleep(LENTO)
    while True:
        datos = conn.recv(4096)
        if not datos:
            break
        conn.sendall(datos)


def main():
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(128)
        print(f'[fork-sig-ign] PADRE pid={os.getpid()} escuchando en {HOST}:{PUERTO}')

        while True:
            conn, direccion = servidor.accept()
            pid = os.fork()

            if pid == 0:
                servidor.close()
                try:
                    atender(conn)
                except (ConnectionResetError, BrokenPipeError):
                    pass
                finally:
                    conn.close()
                    os._exit(0)
            else:
                conn.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido')
