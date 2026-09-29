#!/usr/bin/env python3
"""Variante Parte A2: el PADRE guarda cada `conn` en una lista global en vez
de cerrarla o dejarla caer. A diferencia de "sin_close_padre.py" (donde
CPython puede llegar a cerrar el socket solo al reciclar la variable `conn`
en la vuelta siguiente del loop, por refcounting), acumular en una lista
mantiene una referencia viva a proposito: el fd NO se cierra nunca solo.
"""
import os
import signal
import socket
import sys
import time

HOST = '0.0.0.0'
PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080
LENTO = float(sys.argv[sys.argv.index('--lento') + 1]) if '--lento' in sys.argv else 0.0

conexiones_abiertas = []


def cosechar(signum, frame):
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
        except ChildProcessError:
            break


def atender(conn):
    if LENTO:
        time.sleep(LENTO)
    while True:
        datos = conn.recv(4096)
        if not datos:
            break
        conn.sendall(datos)


def main():
    signal.signal(signal.SIGCHLD, cosechar)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(128)
        print(f'[fork-lista] PADRE pid={os.getpid()} escuchando en {HOST}:{PUERTO}')

        while True:
            try:
                conn, direccion = servidor.accept()
            except InterruptedError:
                continue

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
                # A PROPOSITO: guardamos la referencia en vez de cerrar o
                # dejarla caer, para que ni el refcounting de CPython cierre
                # el fd por su cuenta.
                conexiones_abiertas.append(conn)
                print(f'[fork-lista] conexiones acumuladas: {len(conexiones_abiertas)}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido')
