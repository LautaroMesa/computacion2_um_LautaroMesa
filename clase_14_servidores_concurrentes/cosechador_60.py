#!/usr/bin/env python3
"""Parte C: 60 hijos que mueren exactamente a la vez.

Sin --bucle el handler de SIGCHLD recoge UN hijo por señal. Como las señales
no se encolan (si llegan varias SIGCHLD antes de que corra el handler, el
proceso ve una sola), quedan zombies. Con --bucle el handler recoge todos
los que haya en cada llamada.

Uso:
    python3 cosechador_60.py            # handler sin bucle
    python3 cosechador_60.py --bucle    # handler con while True
"""
import os
import signal
import subprocess
import sys
import time

CON_BUCLE = '--bucle' in sys.argv
N = 60
recogidos = [0]


def cosechar(signum, frame):
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return
        recogidos[0] += 1
        if not CON_BUCLE:
            return          # SIN bucle: uno por señal


signal.signal(signal.SIGCHLD, cosechar)

for _ in range(N):
    if os.fork() == 0:
        time.sleep(0.5)     # todos duermen lo mismo: mueren juntos
        os._exit(0)

# sleep puede cortarse antes de tiempo por la señal; se completa en un loop
fin = time.monotonic() + 2.0
while (resto := fin - time.monotonic()) > 0:
    time.sleep(resto)

salida = subprocess.run(['ps', '--ppid', str(os.getpid()), '-o', 'stat='],
                        capture_output=True, text=True).stdout
zombies = sum(1 for l in salida.splitlines() if l.strip().startswith('Z'))
modo = 'con bucle' if CON_BUCLE else 'sin bucle'
print(f'{modo}: hijos={N}  recogidos={recogidos[0]}  zombies={zombies}')
