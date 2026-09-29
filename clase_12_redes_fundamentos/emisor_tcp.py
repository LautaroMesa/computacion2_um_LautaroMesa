#!/usr/bin/env python3
"""Manda b'HOLA', b'COMO', b'ESTAS' con tres send() separados.

Uso:
    python3 emisor_tcp.py [--pausa SEGUNDOS] [puerto]
"""
import socket
import sys
import time

PAUSA = float(sys.argv[sys.argv.index('--pausa') + 1]) if '--pausa' in sys.argv else 0.0
PUERTO = int(sys.argv[-1]) if len(sys.argv) > 1 and sys.argv[-1].isdigit() else 8080

with socket.create_connection(('localhost', PUERTO)) as s:
    for msg in (b'HOLA', b'COMO', b'ESTAS'):
        s.send(msg)
        if PAUSA:
            time.sleep(PAUSA)
