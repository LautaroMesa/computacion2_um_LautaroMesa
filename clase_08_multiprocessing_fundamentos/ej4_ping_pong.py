#!/usr/bin/env python3
"""Ejercicio 4: padre e hijo se mandan 5 mensajes alternados por un Pipe()
bidireccional (duplex=True es el default)."""
from multiprocessing import Pipe, Process

RONDAS = 5


def hijo(conn):
    for _ in range(RONDAS):
        msg = conn.recv()
        print(f"  hijo  recibio: {msg}", flush=True)
        conn.send(f"pong {msg.split()[1]}")
    conn.close()


if __name__ == "__main__":
    extremo_padre, extremo_hijo = Pipe()
    p = Process(target=hijo, args=(extremo_hijo,))
    p.start()
    extremo_hijo.close()        # el padre no usa el extremo del hijo

    for i in range(1, RONDAS + 1):
        extremo_padre.send(f"ping {i}")
        print(f"padre recibio: {extremo_padre.recv()}", flush=True)

    p.join()
