#!/usr/bin/env python3
"""Pruebas de los dos servidores de framing en los casos extremos.

Con los dos servidores corriendo (servidor_lineas.py en 8080 y
servidor_longitud.py en 8081), corre:

  Delimitador:
    - todo junto:     b'uno\\ndos\\ntres\\n' en un solo sendall()
    - byte por byte:  b'hola\\n' de a un byte con sleep(0.2)
    - con \\n adentro: b'linea1\\nlinea2' pensado como UN mensaje
  Longitud:
    - todo junto:     tres mensajes armados y mandados en un solo sendall()
    - byte por byte:  cabecera + payload de a un byte con sleep(0.05)
    - con \\n adentro: b'linea1\\nlinea2' como un mensaje
    - mensaje vacio:  b''
    - binario:        los 256 valores de byte

Cada prueba dice OK si recibio exactamente las respuestas esperadas.

Uso:
    python3 probar_framing.py [host]
"""
import socket
import sys
import time

from servidor_longitud import CABECERA, enviar_mensaje, recibir_mensaje

HOST = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
PUERTO_LINEAS = 8080
PUERTO_LONGITUD = 8081


def leer_lineas(sock, cantidad):
    """Lee `cantidad` lineas de respuesta (con su propio buffer)."""
    buffer = b''
    lineas = []
    while len(lineas) < cantidad:
        pedazo = sock.recv(4096)
        if not pedazo:
            break
        buffer += pedazo
        while b'\n' in buffer and len(lineas) < cantidad:
            linea, buffer = buffer.split(b'\n', 1)
            lineas.append(linea)
    return lineas


def reportar(nombre, obtenido, esperado, falla_esperada=False):
    """falla_esperada: la prueba muestra una limitacion conocida del esquema
    (no un bug de la implementacion)."""
    if obtenido == esperado:
        estado = 'OK   '
    else:
        estado = 'LIMIT' if falla_esperada else 'FALLA'
    print(f'  [{estado}] {nombre}')
    print(f'          respuestas: {abreviar(obtenido)}')
    if obtenido != esperado:
        print(f'          esperadas:  {abreviar(esperado)}')


def abreviar(mensajes, largo=60):
    r = repr(mensajes)
    return r if len(r) <= largo else r[:largo] + '...]'



def pruebas_lineas():
    print(f'Delimitador (\\n) -> {HOST}:{PUERTO_LINEAS}')

    with socket.create_connection((HOST, PUERTO_LINEAS), timeout=5) as s:
        s.sendall(b'uno\ndos\ntres\n')
        reportar('todo junto en un sendall()', leer_lineas(s, 3),
                 [b'UNO', b'DOS', b'TRES'])

    with socket.create_connection((HOST, PUERTO_LINEAS), timeout=5) as s:
        for b in b'hola\n':
            s.sendall(bytes([b]))
            time.sleep(0.2)
        reportar('byte por byte (sleep 0.2)', leer_lineas(s, 1), [b'HOLA'])

    with socket.create_connection((HOST, PUERTO_LINEAS), timeout=5) as s:
        # UN mensaje que contiene el delimitador: el servidor lo parte en dos
        s.sendall(b'linea1\nlinea2' + b'\n')
        reportar('mensaje con \\n adentro (se espera 1 respuesta)',
                 leer_lineas(s, 2), [b'LINEA1\nLINEA2'], falla_esperada=True)


def pruebas_longitud():
    print(f'\nLongitud (4 bytes !I) -> {HOST}:{PUERTO_LONGITUD}')

    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        mensajes = [b'uno', b'dos', b'tres']
        s.sendall(b''.join(CABECERA.pack(len(m)) + m for m in mensajes))
        reportar('todo junto en un sendall()',
                 [recibir_mensaje(s) for _ in mensajes], [b'UNO', b'DOS', b'TRES'])

    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        trama = CABECERA.pack(4) + b'hola'
        for b in trama:
            s.sendall(bytes([b]))
            time.sleep(0.05)
        reportar('byte por byte, cabecera incluida (sleep 0.05)',
                 [recibir_mensaje(s)], [b'HOLA'])

    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        enviar_mensaje(s, b'linea1\nlinea2')
        reportar('mensaje con \\n adentro', [recibir_mensaje(s)], [b'LINEA1\nLINEA2'])

    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        enviar_mensaje(s, b'')
        enviar_mensaje(s, b'despues del vacio')
        reportar('mensaje vacio (y uno despues)',
                 [recibir_mensaje(s), recibir_mensaje(s)], [b'', b'DESPUES DEL VACIO'])

    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        binario = bytes(range(256))
        enviar_mensaje(s, binario)
        reportar('binario (los 256 valores de byte)',
                 [recibir_mensaje(s)], [binario.upper()])


if __name__ == '__main__':
    pruebas_lineas()
    pruebas_longitud()
