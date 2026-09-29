#!/usr/bin/env python3
"""Parte D: servidor de comandos con un contador GLOBAL de conexiones.

Basado en comandos.py de la catedra, reducido a lo necesario. El contador es
una variable de modulo que cada handler incrementa en setup(). Se puede
levantar con threads o con procesos para ver la diferencia.

Comandos: CONTADOR, PID, QUIT

Uso:
    python3 comandos_contador.py [puerto]          # ThreadingTCPServer
    python3 comandos_contador.py --fork [puerto]   # ForkingTCPServer
"""
import os
import socketserver
import sys
import threading

contador = 0                       # estado global del modulo
lock = threading.Lock()


class Handler(socketserver.StreamRequestHandler):

    def setup(self):
        global contador
        super().setup()
        with lock:
            contador += 1

    def responder(self, texto):
        self.wfile.write((texto + '\n').encode())

    def handle(self):
        for linea in self.rfile:
            cmd = linea.decode('utf-8', 'replace').strip().upper()
            if cmd == 'CONTADOR':
                with lock:
                    n = contador
                self.responder(f'Conexiones totales: {n}')
            elif cmd == 'PID':
                self.responder(f'pid={os.getpid()} hilo={threading.current_thread().name}')
            elif cmd == 'QUIT':
                return
            elif cmd:
                self.responder(f'Comando desconocido: {cmd}')


class ServidorThreads(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ServidorFork(socketserver.ForkingTCPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    usar_fork = '--fork' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    puerto = int(args[0]) if args else 8080
    Servidor = ServidorFork if usar_fork else ServidorThreads
    with Servidor(('0.0.0.0', puerto), Handler) as srv:
        print(f'{Servidor.__name__} en :{puerto} (pid {os.getpid()})', flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
