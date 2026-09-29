#!/usr/bin/env python3
"""Ejercicio 3: productor genera 10 items, consumidor los procesa, via
multiprocessing.Queue. El fin se avisa con un centinela (None)."""
import os
import random
import time
from multiprocessing import Process, Queue

FIN = None


def productor(q, n):
    for i in range(n):
        item = random.randint(1, 100)
        q.put(item)
        print(f"[productor {os.getpid()}] puso {item}", flush=True)
        time.sleep(random.uniform(0.05, 0.2))
    q.put(FIN)


def consumidor(q):
    procesados = 0
    while True:
        item = q.get()          # bloquea hasta que haya algo
        if item is FIN:
            break
        print(f"    [consumidor {os.getpid()}] {item}^2 = {item * item}", flush=True)
        procesados += 1
    print(f"    [consumidor] termino, proceso {procesados} items")


if __name__ == "__main__":
    q = Queue()
    prod = Process(target=productor, args=(q, 10))
    cons = Process(target=consumidor, args=(q,))
    prod.start()
    cons.start()
    prod.join()
    cons.join()
