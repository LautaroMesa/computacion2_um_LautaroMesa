#!/usr/bin/env python3
"""Readers-Writers Lock con preferencia a escritores.

Reglas:
- Multiples lectores pueden leer simultaneamente
- Solo un escritor puede escribir a la vez
- Mientras hay escritor, no puede haber lectores
- Mientras hay lectores, no puede haber escritores

Diferencia con el esqueleto de la consigna: un lector nuevo tambien espera
si hay algun escritor ESPERANDO (writers_waiting > 0), no solo si hay uno
escribiendo. Sin eso, con lectores que se superponen todo el tiempo el
contador `readers` nunca llega a 0 y el escritor espera para siempre
(starvation). Ver demo_starvation.py.
"""
import threading


class ReadWriteLock:
    def __init__(self, preferir_escritores=True):
        self.readers = 0              # lectores leyendo ahora
        self.writers = 0              # 0 o 1: escritor escribiendo ahora
        self.writers_waiting = 0      # escritores esperando turno
        self.preferir_escritores = preferir_escritores
        self.lock = threading.Lock()
        # Las dos Condition comparten el mismo lock: el estado de arriba se
        # lee y modifica siempre con ese lock tomado.
        self.can_read = threading.Condition(self.lock)
        self.can_write = threading.Condition(self.lock)

    def _lector_debe_esperar(self):
        if self.writers > 0:
            return True
        return self.preferir_escritores and self.writers_waiting > 0

    def acquire_read(self):
        with self.lock:
            # while y no if: al despertar hay que volver a chequear, otro
            # hilo pudo haber tomado el lock entre el notify y este despertar.
            while self._lector_debe_esperar():
                self.can_read.wait()
            self.readers += 1

    def release_read(self):
        with self.lock:
            self.readers -= 1
            if self.readers == 0:
                self.can_write.notify()

    def acquire_write(self):
        with self.lock:
            self.writers_waiting += 1
            while self.readers > 0 or self.writers > 0:
                self.can_write.wait()
            self.writers_waiting -= 1
            self.writers += 1

    def release_write(self):
        with self.lock:
            self.writers -= 1
            if self.preferir_escritores and self.writers_waiting > 0:
                # hay escritores en cola: pasa el siguiente escritor
                self.can_write.notify()
            else:
                # se despierta a TODOS los lectores (pueden entrar juntos) y
                # a un escritor por si no habia lectores esperando
                self.can_read.notify_all()
                self.can_write.notify()

    # Atajos: `with rw.leyendo():` / `with rw.escribiendo():`
    def leyendo(self):
        return ReadLock(self)

    def escribiendo(self):
        return WriteLock(self)


class ReadLock:
    def __init__(self, rwlock):
        self.rwlock = rwlock

    def __enter__(self):
        self.rwlock.acquire_read()
        return self

    def __exit__(self, *args):
        self.rwlock.release_read()


class WriteLock:
    def __init__(self, rwlock):
        self.rwlock = rwlock

    def __enter__(self):
        self.rwlock.acquire_write()
        return self

    def __exit__(self, *args):
        self.rwlock.release_write()
