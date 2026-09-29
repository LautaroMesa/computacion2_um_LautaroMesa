#!/usr/bin/env python3
"""Un event loop cooperativo escrito desde cero, con generadores.

Modos:
    python3 mi_scheduler.py intercalado      # Parte A: tres tareas de distinto largo
    python3 mi_scheduler.py sin-yield        # Parte A.3: una tarea sin ningun yield
    python3 mi_scheduler.py egoista          # Parte B: una tarea que no cede por 3 s
    python3 mi_scheduler.py tiempo [N]       # Parte C: tareas que duermen (N corridas)
    python3 mi_scheduler.py sin-yield-from   # Parte D: dormir() sin yield from
"""
import heapq
import itertools
import sys
import time
from collections import deque

T0 = time.monotonic()


def t():
    return f'{time.monotonic() - T0:5.2f}s'


# ---------------------------------------------------------------
# Parte A y B: intercalar
# ---------------------------------------------------------------

def tarea(nombre, pasos):
    for i in range(1, pasos + 1):
        print(f'  {t()} [{nombre}] paso {i}/{pasos}')
        yield                          # cedo el control al scheduler
    print(f'  {t()} [{nombre}] terminada')


def tarea_sin_yield(nombre):
    print(f'  {t()} [{nombre}] hago todo de una')
    return 'resultado'
    yield                              # nunca se ejecuta, pero hace que la funcion
                                       # sea un generador: sin esta linea, llamarla
                                       # correria todo YA y devolveria un str


def tarea_egoista(nombre):
    print(f'  {t()} [{nombre}] me pongo a calcular')
    time.sleep(3)                      # no cede: bloquea al scheduler entero
    print(f'  {t()} [{nombre}] listo')
    yield


def scheduler(tareas):
    """Round-robin: saca una tarea, la reanuda hasta su proximo yield y, si
    no termino, la manda al final de la cola. Devuelve cuantos next() hizo."""
    pendientes = deque(tareas)
    llamadas = 0
    while pendientes:
        tarea_actual = pendientes.popleft()
        llamadas += 1
        try:
            next(tarea_actual)
        except StopIteration:
            continue                   # termino: no vuelve a la cola
        pendientes.append(tarea_actual)
    return llamadas


# ---------------------------------------------------------------
# Parte C y D: el scheduler entiende de tiempo
# ---------------------------------------------------------------

def dormir(segundos):
    """No duerme: le cede el control al scheduler diciendole CUANDO quiere
    que lo despierten. El que espera es el scheduler, no la tarea."""
    yield time.monotonic() + segundos


def tarea_lenta(nombre, veces, espera=0.15):
    for i in range(1, veces + 1):
        print(f'  {t()} [{nombre}] {i}/{veces}')
        yield from dormir(espera)
    print(f'  {t()} [{nombre}] terminada')


def tarea_lenta_sin_yield_from(nombre, veces, espera=0.15):
    for i in range(1, veces + 1):
        print(f'  {t()} [{nombre}] {i}/{veces}')
        dormir(espera)                 # crea el generador y lo tira: no cede nada
    print(f'  {t()} [{nombre}] terminada')
    yield                              # para que siga siendo un generador


def scheduler_con_tiempo(tareas):
    """Cola de prioridad por hora de despertar (heap).

    A diferencia de un scheduler que recorre la cola preguntando "¿ya te
    toca?", este no gira en vacio: si nadie esta listo, duerme exactamente
    hasta la proxima hora de despertar. Es lo que hace el event loop de
    asyncio con el timeout de epoll/select.
    """
    desempate = itertools.count()      # el heap no puede comparar generadores
    listas = [(0.0, next(desempate), tr) for tr in tareas]
    heapq.heapify(listas)
    llamadas = 0
    dormido = 0.0
    while listas:
        despertar, _, tarea_actual = heapq.heappop(listas)
        falta = despertar - time.monotonic()
        if falta > 0:
            time.sleep(falta)          # el SCHEDULER duerme, nadie tiene nada que hacer
            dormido += falta
        llamadas += 1
        try:
            cuando = next(tarea_actual)
        except StopIteration:
            continue
        heapq.heappush(listas, (cuando or 0.0, next(desempate), tarea_actual))
    return llamadas, dormido


# ---------------------------------------------------------------

def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else 'intercalado'

    if modo == 'intercalado':
        n = scheduler([tarea('A', 3), tarea('B', 1), tarea('C', 5)])
        print(f'\nnext() en total: {n}  (pasos 3+1+5 = 9, mas 1 por tarea para terminar = 12)')

    elif modo == 'sin-yield':
        n = scheduler([tarea('A', 2), tarea_sin_yield('S'), tarea('B', 2)])
        print(f'\nnext() en total: {n}')

    elif modo == 'egoista':
        inicio = time.monotonic()
        scheduler([tarea('A', 3), tarea_egoista('EGO'), tarea('B', 3)])
        print(f'\nTotal: {time.monotonic() - inicio:.2f}s')

    elif modo == 'tiempo':
        corridas = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        for _ in range(corridas):
            inicio = time.monotonic()
            n, dormido = scheduler_con_tiempo([tarea_lenta('A', 3), tarea_lenta('B', 3),
                                               tarea_lenta('C', 3)])
            total = time.monotonic() - inicio
            print(f'\nTotal: {total:.3f}s  (suma de esperas: 9 x 0.15 = 1.35s; '
                  f'next(): {n}; el scheduler durmio {dormido:.3f}s)\n')

    elif modo == 'sin-yield-from':
        inicio = time.monotonic()
        scheduler_con_tiempo([tarea_lenta_sin_yield_from('A', 3),
                              tarea_lenta_sin_yield_from('B', 3)])
        print(f'\nTotal: {time.monotonic() - inicio:.3f}s  (deberia ser ~0.45s si durmiera)')


if __name__ == '__main__':
    main()
