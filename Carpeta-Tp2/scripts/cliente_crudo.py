"""Cliente HTTP/1.1 mínimo con asyncio.open_connection (clases 13 y 20).

Para mandar miles de POST sin que el cliente sea el cuello de botella:
httpx es cómodo, pero arma y parsea cada pedido en Python y cuesta ~1-2 ms
de CPU por pedido. Este cliente reutiliza la conexión (keep-alive) y lee la
respuesta con framing por Content-Length, sin nada más.
"""
import asyncio
import json
from urllib.parse import urlsplit


class ConexionCruda:
    def __init__(self, reader, writer, host):
        self.reader, self.writer, self.host = reader, writer, host

    @classmethod
    async def abrir(cls, api):
        u = urlsplit(api)
        reader, writer = await asyncio.open_connection(u.hostname, u.port or 80)
        return cls(reader, writer, f'{u.hostname}:{u.port or 80}')

    async def pedir(self, metodo, ruta, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else b''
        cabecera = (f'{metodo} {ruta} HTTP/1.1\r\nHost: {self.host}\r\n'
                    f'Content-Type: application/json\r\nContent-Length: {len(datos)}\r\n\r\n')
        self.writer.write(cabecera.encode() + datos)
        await self.writer.drain()
        # Cabeceras hasta la línea vacía (delimitador), cuerpo por longitud
        cab = await self.reader.readuntil(b'\r\n\r\n')
        codigo = int(cab.split(b' ', 2)[1])
        largo = 0
        for linea in cab.split(b'\r\n'):
            if linea.lower().startswith(b'content-length:'):
                largo = int(linea.split(b':', 1)[1])
        cuerpo_resp = await self.reader.readexactly(largo)
        return codigo, cuerpo_resp

    async def cerrar(self):
        self.writer.close()
        await self.writer.wait_closed()


async def muchos_post(api, ruta, cuerpo, n, conexiones):
    """Manda n POST repartidos en `conexiones` conexiones keep-alive.
    Devuelve {codigo_http: cantidad}."""
    codigos = {}
    restantes = n

    async def por_conexion():
        nonlocal restantes
        c = await ConexionCruda.abrir(api)
        try:
            while restantes > 0:
                restantes -= 1          # sin await en el medio: sin carrera
                codigo, _ = await c.pedir('POST', ruta, cuerpo)
                codigos[codigo] = codigos.get(codigo, 0) + 1
        finally:
            await c.cerrar()

    await asyncio.gather(*(por_conexion() for _ in range(min(conexiones, n))))
    return codigos
