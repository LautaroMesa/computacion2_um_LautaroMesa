#!/usr/bin/env python3
"""Servidor con framing por delimitador ('\\n').

Recibe mensajes terminados en '\\n' y responde cada uno en mayusculas,
tambien terminado en '\\n'. Atiende de a un cliente (secuencial).

Uso:
    python3 servidor_lineas.py [puerto]
    nc localhost 8080       # y escribir lineas
"""
import socket
import sys

HOST = '0.0.0.0'
PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
DELIM = b'\n'
# Sin un tope, un cliente que manda bytes sin '\n' nunca hace crecer el
# buffer hasta llenar la memoria del servidor.
MAX_LINEA = 64 * 1024


class LineaDemasiadoLarga(Exception):
    pass


def recibir_lineas(sock):
    """Generador de lineas completas (sin el '\\n').

    El buffer sobrevive entre llamadas a recv(): un recv() puede traer media
    linea (queda esperando el resto) o tres lineas y media (se entregan las
    tres y la media queda en el buffer para la proxima vuelta).
    """
    buffer = b''
    while True:
        pedazo = sock.recv(4096)
        if not pedazo:
            if buffer:
                # el cliente cerro con una linea a medio mandar: no es un
                # mensaje completo, asi que no se entrega
                print(f'  (descartados {len(buffer)} bytes sin \\n al cerrar)')
            return
        buffer += pedazo
        while DELIM in buffer:
            linea, buffer = buffer.split(DELIM, 1)
            yield linea
        if len(buffer) > MAX_LINEA:
            raise LineaDemasiadoLarga(f'mas de {MAX_LINEA} bytes sin \\n')


def atender(conn, direccion):
    n = 0
    for linea in recibir_lineas(conn):
        n += 1
        print(f'  [{direccion[1]}] mensaje {n}: {linea!r}')
        conn.sendall(linea.upper() + DELIM)
    print(f'  [{direccion[1]}] cerro tras {n} mensajes')


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(5)
        print(f'[lineas] Escuchando en {HOST}:{PUERTO}', flush=True)
        while True:
            conn, direccion = servidor.accept()
            print(f'Conexion desde {direccion}', flush=True)
            try:
                with conn:
                    atender(conn, direccion)
            except (ConnectionResetError, BrokenPipeError, LineaDemasiadoLarga) as e:
                print(f'  [{direccion[1]}] conexion cortada: {e}')
            sys.stdout.flush()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido')
