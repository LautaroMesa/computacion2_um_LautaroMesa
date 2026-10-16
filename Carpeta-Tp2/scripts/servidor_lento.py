#!/usr/bin/env python3
"""Servidor HTTP mínimo que responde con una demora elegida.

Sirve para medir `descargar` sin depender de internet: con una demora fija
y conocida, la diferencia entre secuencial y concurrente es reproducible.

Está hecho con asyncio.start_server (clase 20) y HTTP/1.1 a mano (clase 19),
sin frameworks:

    GET /demora/<segundos>[?bytes=N]   espera y responde N bytes (default 1000)

Uso:
    python3 scripts/servidor_lento.py [puerto]      # default 8081
"""
import asyncio
import sys
from urllib.parse import parse_qs, urlsplit

MAX_DEMORA = 60.0
MAX_BYTES = 10 * 1024 * 1024


def respuesta(codigo, razon, cuerpo=b'', cerrar=False):
    cabeceras = [
        f'HTTP/1.1 {codigo} {razon}',
        'Content-Type: application/octet-stream',
        f'Content-Length: {len(cuerpo)}',
        f'Connection: {"close" if cerrar else "keep-alive"}',
    ]
    return ('\r\n'.join(cabeceras) + '\r\n\r\n').encode() + cuerpo


async def atender(reader, writer):
    try:
        while True:
            # Framing por delimitador para la cabecera (clase 13): hasta la línea vacía
            try:
                cabecera = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout=30)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
                return
            linea = cabecera.split(b'\r\n', 1)[0].decode('latin-1')
            try:
                metodo, ruta, _ = linea.split(' ', 2)
                partes = urlsplit(ruta)
                tramos = partes.path.strip('/').split('/')
                if metodo != 'GET' or len(tramos) != 2 or tramos[0] != 'demora':
                    raise ValueError
                demora = min(float(tramos[1]), MAX_DEMORA)
                n = min(int(parse_qs(partes.query).get('bytes', ['1000'])[0]), MAX_BYTES)
            except ValueError:
                writer.write(respuesta(404, 'Not Found', b'usar GET /demora/<segundos>', cerrar=True))
                await writer.drain()
                return
            await asyncio.sleep(demora)       # la demora NO bloquea a los demás clientes
            writer.write(respuesta(200, 'OK', b'x' * n))
            await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


async def main(puerto):
    servidor = await asyncio.start_server(atender, '0.0.0.0', puerto)
    print(f'servidor lento en :{puerto}  (GET /demora/<segundos>?bytes=N)', flush=True)
    async with servidor:
        await servidor.serve_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8081))
    except KeyboardInterrupt:
        pass
