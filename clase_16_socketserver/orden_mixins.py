#!/usr/bin/env python3
"""Parte B: el mismo servidor con el mixin bien puesto y al reves.

El handler tarda LENTO segundos por cliente, asi se nota si atiende en
paralelo o de a uno. Probarlo con clientes_lentos.py.

Uso:
    python3 orden_mixins.py secuencial [puerto]   # TCPServer solo, sin mixin
    python3 orden_mixins.py correcto [puerto]
    python3 orden_mixins.py alreves  [puerto]
"""
import socketserver
import sys
import threading
import time

LENTO = 2.0


class HandlerLento(socketserver.StreamRequestHandler):
    def handle(self):
        linea = self.rfile.readline()
        print(f'  atendiendo {self.client_address[1]} en {threading.current_thread().name}',
              flush=True)
        time.sleep(LENTO)
        self.wfile.write(linea.upper())


class Secuencial(socketserver.TCPServer):
    allow_reuse_address = True


class Correcto(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class AlReves(socketserver.TCPServer, socketserver.ThreadingMixIn):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else 'correcto'
    puerto = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    Servidor = {'secuencial': Secuencial, 'correcto': Correcto, 'alreves': AlReves}[modo]
    with Servidor(('0.0.0.0', puerto), HandlerLento) as srv:
        print(f'[{modo}] {[c.__name__ for c in Servidor.__mro__][:3]} en :{puerto}', flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
