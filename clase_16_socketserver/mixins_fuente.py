#!/usr/bin/env python3
"""Partes A y B: que definen los mixins y en que orden se buscan los metodos.

Imprime los metodos que define cada mixin, quien termina resolviendo
process_request en cada clase, y el MRO de una clase con el orden correcto
y otra con el orden invertido.
"""
import inspect
import socketserver


def metodos_propios(cls):
    return [n for n, v in vars(cls).items() if inspect.isfunction(v)]


def quien_resuelve(cls, nombre):
    """La primera clase del MRO que define `nombre`."""
    for c in cls.__mro__:
        if nombre in vars(c):
            return c.__name__


class Correcto(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


class AlReves(socketserver.TCPServer, socketserver.ThreadingMixIn):
    pass


if __name__ == '__main__':
    print('== Parte A: metodos propios de cada mixin')
    for mixin in (socketserver.ThreadingMixIn, socketserver.ForkingMixIn):
        print(f'{mixin.__name__}: {metodos_propios(mixin)}')

    print('\n== process_request: quien lo define')
    for cls in (socketserver.BaseServer, socketserver.TCPServer,
                socketserver.ThreadingMixIn, socketserver.ForkingMixIn):
        print(f'  {cls.__name__:<15} lo define: {"process_request" in vars(cls)}')

    print('\n== Parte B: MRO')
    for cls in (Correcto, AlReves):
        print(f'{cls.__name__:<9} {[c.__name__ for c in cls.__mro__]}')
        print(f'          process_request -> {quien_resuelve(cls, "process_request")}')
        print(f'          server_close    -> {quien_resuelve(cls, "server_close")}')
