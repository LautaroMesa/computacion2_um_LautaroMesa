#!/usr/bin/env python3
"""Servidor con framing por prefijo de longitud.

Cada mensaje es: 4 bytes big-endian con el largo (struct '!I') + payload.
Responde cada mensaje en mayusculas con el mismo formato. Atiende de a un
cliente (secuencial).

Uso:
    python3 servidor_longitud.py [puerto]

Las funciones de framing (recibir_exacto, enviar_mensaje, recibir_mensaje)
las usa tambien probar_framing.py del lado del cliente.
"""
import socket
import struct
import sys

HOST = '0.0.0.0'
PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
CABECERA = struct.Struct('!I')        # '!' = orden de red (big-endian)
# La cabecera la escribe el cliente: sin tope, un largo de 4 GB (o una
# cabecera corrupta) haria que el servidor intente juntar 4 GB en memoria.
MAX_MENSAJE = 16 * 1024 * 1024


class MensajeDemasiadoGrande(Exception):
    pass


def recibir_exacto(sock, n):
    """Lee EXACTAMENTE n bytes, o devuelve None si cerraron antes.

    recv(n) devuelve HASTA n bytes: lo que haya disponible en ese momento.
    Por eso hay que insistir hasta completar.
    """
    partes = []
    faltan = n
    while faltan > 0:
        pedazo = sock.recv(min(faltan, 65536))
        if not pedazo:
            return None
        partes.append(pedazo)
        faltan -= len(pedazo)
    return b''.join(partes)


def enviar_mensaje(sock, payload: bytes):
    # Un solo sendall con cabecera + payload: con dos send() separados
    # funcionaria igual (es un flujo), pero serian dos syscalls.
    sock.sendall(CABECERA.pack(len(payload)) + payload)


def recibir_mensaje(sock):
    """Devuelve el payload del proximo mensaje, o None si cerraron.

    Ojo: un mensaje vacio (b'') es valido y distinto de None.
    """
    cabecera = recibir_exacto(sock, CABECERA.size)
    if cabecera is None:
        return None
    (largo,) = CABECERA.unpack(cabecera)
    if largo > MAX_MENSAJE:
        raise MensajeDemasiadoGrande(f'{largo} bytes (maximo {MAX_MENSAJE})')
    if largo == 0:
        return b''
    payload = recibir_exacto(sock, largo)
    if payload is None:
        # cerraron en medio del mensaje: la cabecera prometia mas bytes
        raise ConnectionResetError(f'cierre a mitad de un mensaje de {largo} bytes')
    return payload


def atender(conn, direccion):
    n = 0
    while True:
        mensaje = recibir_mensaje(conn)
        if mensaje is None:
            break
        n += 1
        print(f'  [{direccion[1]}] mensaje {n} ({len(mensaje)} bytes): {mensaje[:60]!r}')
        enviar_mensaje(conn, mensaje.upper())
    print(f'  [{direccion[1]}] cerro tras {n} mensajes')


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(5)
        print(f'[longitud] Escuchando en {HOST}:{PUERTO}', flush=True)
        while True:
            conn, direccion = servidor.accept()
            print(f'Conexion desde {direccion}', flush=True)
            try:
                with conn:
                    atender(conn, direccion)
            except (ConnectionResetError, BrokenPipeError, MensajeDemasiadoGrande) as e:
                print(f'  [{direccion[1]}] conexion cortada: {e}')
            sys.stdout.flush()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido')
