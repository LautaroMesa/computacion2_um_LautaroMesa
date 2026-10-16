"""Implementación de cada tipo de tarea.

Cada ejecutor es una corrutina que recibe la Tarea y devuelve su resultado
(algo serializable a JSON). Si lanza una excepción, el pool la marca como
fallida; si la cancelan, como cancelada.
"""
import asyncio
import time


async def esperar(tarea):
    """I/O simulado: dormir N segundos sin bloquear el loop.

    asyncio.sleep cede el control al event loop (clase 18: es el dormir() del
    scheduler hecho a mano). time.sleep acá congelaría a todo el servidor.
    """
    segundos = tarea.parametros['segundos']
    inicio = time.monotonic()
    tarea.progreso = 0.0
    # De a pasos cortos para que GET /tareas/{id} muestre el progreso en vivo
    while (transcurrido := time.monotonic() - inicio) < segundos:
        tarea.progreso = round(transcurrido / segundos, 3)
        await asyncio.sleep(min(0.25, segundos - transcurrido))
    return {'durmio': round(time.monotonic() - inicio, 3)}


def armar_ejecutores():
    return {'esperar': esperar}
