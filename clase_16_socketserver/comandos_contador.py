#!/usr/bin/env python3
"""Parte C: contador de conexiones con threads, con fork, y con fork +
multiprocessing.Value.

Basado en comandos.py de la catedra, reducido a lo necesario. Cada handler
incrementa el contador en setup().

  threads          contador = int en el servidor + threading.Lock -> funciona
  --fork           el mismo int, pero cada hijo incrementa SU copia -> siempre 1
  --fork --value   el contador es un multiprocessing.Value creado en el
                   __init__ del servidor, ANTES de que haya hijos: los hijos
                   heredan la misma memoria compartida -> funciona

Comandos: CONTADOR, PID, QUIT

Uso:
    python3 comandos_contador.py [puerto]
    python3 comandos_contador.py --fork [puerto]
    python3 comandos_contador.py --fork --value [puerto]
"""
import multiprocessing
import os
import socketserver
import sys
import threading


class Handler(socketserver.StreamRequestHandler):

    def setup(self):
        super().setup()
        self.server.incrementar()

    def responder(self, texto):
        self.wfile.write((texto + '\n').encode())

    def handle(self):
        for linea in self.rfile:
            cmd = linea.decode('utf-8', 'replace').strip().upper()
            if cmd == 'CONTADOR':
                self.responder(f'Conexiones totales: {self.server.leer()}')
            elif cmd == 'PID':
                self.responder(f'pid={os.getpid()} hilo={threading.current_thread().name}')
            elif cmd == 'QUIT':
                return
            elif cmd:
                self.responder(f'Comando desconocido: {cmd}')


class ContadorLocal:
    """Un int comun y un threading.Lock: sirve entre threads del mismo proceso."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.contador = 0
        self.lock = threading.Lock()

    def incrementar(self):
        with self.lock:
            self.contador += 1

    def leer(self):
        with self.lock:
            return self.contador


class ContadorCompartido:
    """multiprocessing.Value: memoria compartida entre procesos.

    Se crea aca, en el __init__ del servidor, que corre en el padre ANTES
    del primer fork(). Cada hijo hereda el mapeo de esa misma memoria. Si se
    creara en el handler, cada hijo crearia un Value nuevo que solo el ve.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.contador = multiprocessing.Value('i', 0)

    def incrementar(self):
        # get_lock(): el += son dos accesos (leer y escribir), ver clase 7
        with self.contador.get_lock():
            self.contador.value += 1

    def leer(self):
        with self.contador.get_lock():
            return self.contador.value


class ServidorThreads(ContadorLocal, socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ServidorFork(ContadorLocal, socketserver.ForkingTCPServer):
    allow_reuse_address = True


class ServidorForkValue(ContadorCompartido, socketserver.ForkingTCPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    puerto = int(args[0]) if args else 8080
    if '--fork' in sys.argv:
        Servidor = ServidorForkValue if '--value' in sys.argv else ServidorFork
    else:
        Servidor = ServidorThreads
    with Servidor(('0.0.0.0', puerto), Handler) as srv:
        print(f'{Servidor.__name__} en :{puerto} (pid {os.getpid()})', flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
