#!/usr/bin/env python3
"""Protocolo confiable sobre UDP: reintentos + numeros de secuencia.

Levanta un servidor (en un thread) que pasa mensajes a mayusculas y un
cliente que le manda N mensajes. Las perdidas se simulan en LAS DOS
direcciones (se puede perder el pedido o la respuesta) con
sendto_con_perdidas() de perdidas.py.

Modos:
  ingenuo  el cliente reintenta con timeout, pero no hay numeros de secuencia:
           el servidor procesa cada datagrama que le llega (tambien los
           reintentos de pedidos que ya proceso) y el cliente acepta la
           primera respuesta que llegue, sea del intento que sea.
  seq      cada mensaje lleva un seq de 4 bytes (struct '!I'). El servidor
           guarda la respuesta de cada seq: si llega un duplicado la reenvia
           sin volver a hacer el trabajo. El cliente descarta respuestas cuyo
           seq no es el del pedido en curso.

Al final muestra: exitos, envios reales, intentos promedio, cuantas veces el
servidor hizo el trabajo y cuantas respuestas equivocadas acepto el cliente.

Uso:
    python3 udp_confiable.py --modo ingenuo --perdida 0.3
    python3 udp_confiable.py --modo seq --perdida 0.7 --intentos 50
    python3 udp_confiable.py --modo ingenuo --timeout 0.01 --demora 0.02
"""
import argparse
import random
import socket
import struct
import threading
import time

from perdidas import sendto_con_perdidas

SEQ = struct.Struct('!I')          # '!' = orden de red


def empaquetar(seq, payload):
    return SEQ.pack(seq) + payload


def desempaquetar(datos):
    (seq,) = SEQ.unpack(datos[:SEQ.size])
    return seq, datos[SEQ.size:]


# --------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------

class Servidor(threading.Thread):
    def __init__(self, modo, perdida, demora):
        super().__init__(daemon=True)
        self.modo = modo
        self.perdida = perdida
        self.demora = demora
        self.trabajos = 0              # veces que hizo el trabajo "real"
        self.datagramas = 0            # datagramas recibidos
        self.respuestas_guardadas = {} # (cliente, seq) -> respuesta
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', 0))       # puerto libre cualquiera
        self.direccion = self.sock.getsockname()

    def trabajo(self, payload):
        """El trabajo "caro" que no deberia repetirse (pensar: transferir $100)."""
        self.trabajos += 1
        if self.demora:
            time.sleep(self.demora)
        return payload.upper()

    def run(self):
        while True:
            try:
                datos, cliente = self.sock.recvfrom(65535)
            except OSError:
                return                 # socket cerrado: fin
            self.datagramas += 1

            if self.modo == 'ingenuo':
                respuesta = self.trabajo(datos)
            else:
                seq, payload = desempaquetar(datos)
                clave = (cliente, seq)
                if clave not in self.respuestas_guardadas:
                    self.respuestas_guardadas[clave] = empaquetar(seq, self.trabajo(payload))
                # si es duplicado, se reenvia la respuesta guardada sin trabajar
                respuesta = self.respuestas_guardadas[clave]

            sendto_con_perdidas(self.sock, respuesta, cliente, self.perdida)

    def cerrar(self):
        self.sock.close()


# --------------------------------------------------------------------
# Cliente
# --------------------------------------------------------------------

def pedir_con_reintentos(sock, mensaje, destino, intentos, timeout, perdida):
    """Modo ingenuo: manda y reintenta si no llega respuesta a tiempo.
    Devuelve (respuesta o None, envios_hechos)."""
    sock.settimeout(timeout)
    for intento in range(1, intentos + 1):
        sendto_con_perdidas(sock, mensaje, destino, perdida)
        try:
            datos, _ = sock.recvfrom(65535)
            return datos, intento
        except TimeoutError:
            continue
    return None, intentos


def pedir_con_seq(sock, seq, mensaje, destino, intentos, timeout, perdida):
    """Modo seq: igual, pero descarta respuestas que no sean de este seq
    (por ejemplo, una respuesta demorada a un pedido anterior)."""
    trama = empaquetar(seq, mensaje)
    descartadas = 0
    for intento in range(1, intentos + 1):
        sendto_con_perdidas(sock, trama, destino, perdida)
        limite = time.monotonic() + timeout
        while (resto := limite - time.monotonic()) > 0:
            sock.settimeout(resto)
            try:
                datos, _ = sock.recvfrom(65535)
            except TimeoutError:
                break
            seq_resp, payload = desempaquetar(datos)
            if seq_resp == seq:
                return payload, intento, descartadas
            descartadas += 1       # vieja: seguir esperando la correcta
    return None, intentos, descartadas


def main():
    ap = argparse.ArgumentParser(description='Protocolo confiable sobre UDP')
    ap.add_argument('--modo', choices=['ingenuo', 'seq'], default='seq')
    ap.add_argument('--perdida', type=float, default=0.3,
                    help='probabilidad de perder cada datagrama (en cada direccion)')
    ap.add_argument('-n', '--mensajes', type=int, default=50)
    ap.add_argument('--intentos', type=int, default=10)
    ap.add_argument('--timeout', type=float, default=0.5)
    ap.add_argument('--demora', type=float, default=0.0,
                    help='segundos que tarda el servidor en hacer el trabajo')
    ap.add_argument('--semilla', type=int, default=None)
    args = ap.parse_args()
    if args.semilla is not None:
        random.seed(args.semilla)

    srv = Servidor(args.modo, args.perdida, args.demora)
    srv.start()

    exitos = equivocadas = descartadas = envios = 0
    intentos_exitosos = []
    inicio = time.perf_counter()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for i in range(args.mensajes):
            mensaje = b'mensaje %d' % i
            if args.modo == 'ingenuo':
                resp, n = pedir_con_reintentos(sock, mensaje, srv.direccion,
                                               args.intentos, args.timeout, args.perdida)
            else:
                resp, n, d = pedir_con_seq(sock, i, mensaje, srv.direccion,
                                           args.intentos, args.timeout, args.perdida)
                descartadas += d
            envios += n
            if resp is not None:
                exitos += 1
                intentos_exitosos.append(n)
                if resp != mensaje.upper():
                    equivocadas += 1     # acepto la respuesta de OTRO mensaje
    duracion = time.perf_counter() - inicio
    time.sleep(0.1)                      # que el servidor termine lo pendiente
    srv.cerrar()

    prom = sum(intentos_exitosos) / len(intentos_exitosos) if intentos_exitosos else 0
    print(f'modo={args.modo}  perdida={args.perdida:.0%} por direccion  '
          f'timeout={args.timeout}s  intentos max={args.intentos}')
    print(f'  Mensajes:                     {args.mensajes}')
    print(f'  Con respuesta:                {exitos}  '
          f'(sin respuesta tras {args.intentos} intentos: {args.mensajes - exitos})')
    print(f'  Envios reales del cliente:    {envios}')
    print(f'  Intentos promedio (exitosos): {prom:.2f}  (maximo {max(intentos_exitosos, default=0)})')
    print(f'  Datagramas que le llegaron al servidor: {srv.datagramas}')
    print(f'  Veces que el servidor hizo el trabajo:  {srv.trabajos}')
    print(f'  Respuestas equivocadas aceptadas:       {equivocadas}')
    if args.modo == 'seq':
        print(f'  Respuestas viejas descartadas por seq:  {descartadas}')
    print(f'  Tiempo: {duracion:.2f}s')


if __name__ == '__main__':
    main()
