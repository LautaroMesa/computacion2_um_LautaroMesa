#!/usr/bin/env python3
"""Starvation del escritor: preferencia a lectores vs a escritores.

8 lectores leen en loop durante DURACION segundos, con lecturas que se
superponen (siempre hay al menos uno adentro). A los 0.5 s un escritor pide
el lock. Se mide cuanto espera.

- Preferencia a lectores (el esqueleto de la consigna): los lectores nuevos
  entran aunque haya un escritor esperando, `readers` nunca llega a 0 y el
  escritor espera hasta que los lectores se cansan (fin de la prueba).
- Preferencia a escritores: en cuanto el escritor pide, los lectores nuevos
  esperan; se vacian los que estaban y el escritor entra enseguida.
"""
import threading
import time

from rwlock import ReadWriteLock

DURACION = 3.0
NUM_LECTORES = 8


def probar(preferir_escritores):
    rw = ReadWriteLock(preferir_escritores=preferir_escritores)
    fin = time.perf_counter() + DURACION
    espera = {}

    def lector():
        while time.perf_counter() < fin:
            with rw.leyendo():
                time.sleep(0.05)

    def escritor():
        time.sleep(0.5)
        t0 = time.perf_counter()
        with rw.escribiendo():
            espera["seg"] = time.perf_counter() - t0

    hilos = [threading.Thread(target=lector) for _ in range(NUM_LECTORES)]
    hilos.append(threading.Thread(target=escritor))
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    return espera["seg"]


if __name__ == "__main__":
    print(f"{NUM_LECTORES} lectores leyendo sin parar durante {DURACION}s; "
          f"un escritor pide el lock a los 0.5s\n")
    for pref, nombre in ((False, "preferencia a lectores"),
                         (True, "preferencia a escritores")):
        seg = probar(pref)
        print(f"  {nombre:<26} el escritor espero {seg:.3f}s")
