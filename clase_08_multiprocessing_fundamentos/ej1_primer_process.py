#!/usr/bin/env python3
"""Ejercicio 1: el mismo "padre crea un hijo y lo espera" con os.fork() y
con multiprocessing.Process, para comparar las dos APIs."""
import os
from multiprocessing import Process


def trabajo(origen):
    # flush=True: os._exit() sale sin vaciar el buffer de stdout, y si la
    # salida va a un pipe o archivo (no a la terminal) el print se pierde.
    print(f"[{origen}] hijo pid={os.getpid()} ppid={os.getppid()}", flush=True)


def con_fork():
    pid = os.fork()
    if pid == 0:
        trabajo("fork")
        os._exit(0)          # el hijo tiene que salir a mano, si no sigue
                             # ejecutando el resto del programa del padre
    _, status = os.waitpid(pid, 0)
    print(f"[fork] padre: hijo {pid} termino con codigo {os.waitstatus_to_exitcode(status)}")


def con_process():
    p = Process(target=trabajo, args=("Process",))
    p.start()
    p.join()
    print(f"[Process] padre: hijo {p.pid} termino con codigo {p.exitcode}")


if __name__ == "__main__":
    print(f"padre pid={os.getpid()}", flush=True)
    con_fork()
    con_process()
