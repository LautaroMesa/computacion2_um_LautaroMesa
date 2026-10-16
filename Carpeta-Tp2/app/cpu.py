"""Trabajo CPU-bound puro, para correr en un proceso aparte.

Este módulo no importa nada de asyncio ni de la app: lo que se manda a un
ProcessPoolExecutor tiene que poder importarse en el proceso hijo y viajar
pickleado (una función de módulo sí; una lambda o un método de un objeto
con un event loop adentro, no).
"""
import hashlib


def sha256_iterado(datos: bytes, iteraciones: int) -> bytes:
    """Aplica SHA-256 `iteraciones` veces: h = sha256(h).

    No hace ninguna llamada que ceda el control: mientras corre, el hilo que
    la ejecuta está ocupado al 100%. Si ese hilo es el del event loop, la API
    entera queda congelada (medición 2 del TP).
    """
    h = datos
    for _ in range(iteraciones):
        h = hashlib.sha256(h).digest()
    return h
