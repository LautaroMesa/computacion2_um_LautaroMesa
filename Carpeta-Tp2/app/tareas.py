"""Implementación de cada tipo de tarea.

Cada ejecutor es una corrutina que recibe la Tarea y devuelve su resultado
(algo serializable a JSON). Si lanza una excepción, el pool la marca como
fallida; si la cancelan, como cancelada; si vence su timeout, como fallida
por timeout.
"""
import asyncio
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import multiprocessing

import httpx

from .cpu import sha256_iterado

log = logging.getLogger('tp2.tareas')

# Iteraciones de SHA-256 por viaje al executor (~0.1-0.2 s de CPU). Es el
# "grano" de la cancelación: un proceso que ya está calculando no se puede
# interrumpir, así que cancelar o vencer el timeout corta en el borde del
# siguiente bloque y se desperdicia como mucho uno.
BLOQUE_HASH = 250_000

MAX_BYTES_DESCARGA = 50 * 1024 * 1024   # por URL: no traer un archivo de 10 GB a memoria


def _nada():
    return None


class Ejecutores:
    """Las corrutinas de cada tipo, con los recursos que comparten.

    Los recursos caros se crean UNA vez al arrancar y se reutilizan:
      - un httpx.AsyncClient (pool de conexiones keep-alive, clase 20)
      - un ProcessPoolExecutor (arrancar procesos cuesta, clase 21)
    """

    def __init__(self, config):
        self.config = config
        self.cliente: httpx.AsyncClient | None = None
        self.pool_cpu: ProcessPoolExecutor | None = None

    # ---------------------------------------------------------------
    # recursos
    # ---------------------------------------------------------------

    async def abrir(self):
        self.cliente = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=self.config.max_conexiones,
                                max_keepalive_connections=20),
            follow_redirects=True,
            headers={'User-Agent': 'tp2-tareas/1.0 (Computacion II UM)'},
        )
        if self.config.hash_executor == 'proceso':
            await self._crear_pool_cpu()

    async def _crear_pool_cpu(self):
        # 'spawn' en todas las plataformas: el mismo comportamiento en Linux,
        # macOS y Windows, y sin el problema de hacer fork() de un proceso que
        # ya tiene threads (el del executor por defecto, el de uvicorn).
        self.pool_cpu = ProcessPoolExecutor(
            max_workers=self.config.procesos,
            mp_context=multiprocessing.get_context('spawn'),
        )
        # Precalentar: que los procesos arranquen ahora y no en la primera tarea
        loop = asyncio.get_running_loop()
        await asyncio.gather(*(loop.run_in_executor(self.pool_cpu, _nada)
                               for _ in range(self.config.procesos)))
        log.info('pool de procesos listo: %d procesos', self.config.procesos)

    async def cerrar(self):
        if self.cliente is not None:
            await self.cliente.aclose()
        if self.pool_cpu is not None:
            # shutdown(wait=True) BLOQUEA hasta que los procesos terminen el
            # bloque que estén calculando (hasta ~0,2 s): se hace en un thread
            # para no frenar el event loop. cancel_futures: lo que no empezó, no empieza.
            await asyncio.to_thread(self.pool_cpu.shutdown, wait=True, cancel_futures=True)

    def como_dict(self):
        return {'descargar': self.descargar, 'hashear': self.hashear, 'esperar': self.esperar}

    # ---------------------------------------------------------------
    # esperar: I/O simulado
    # ---------------------------------------------------------------

    async def esperar(self, tarea):
        """Dormir N segundos sin bloquear el loop.

        asyncio.sleep cede el control al event loop (el dormir() del scheduler
        de la clase 18). time.sleep acá congelaría a todo el servidor.
        """
        segundos = tarea.parametros['segundos']
        inicio = time.monotonic()
        tarea.progreso = 0.0
        # De a pasos cortos para que GET /tareas/{id} muestre el progreso en vivo
        while (transcurrido := time.monotonic() - inicio) < segundos:
            tarea.progreso = round(transcurrido / segundos, 3)
            await asyncio.sleep(min(0.25, segundos - transcurrido))
        return {'durmio': round(time.monotonic() - inicio, 3)}

    # ---------------------------------------------------------------
    # descargar: I/O-bound real
    # ---------------------------------------------------------------

    async def descargar(self, tarea):
        urls = tarea.parametros['urls']
        hechas = 0
        tarea.progreso = 0.0

        async def una(url):
            nonlocal hechas
            inicio = time.monotonic()
            try:
                tam = 0
                # stream: se cuentan los bytes a medida que llegan, sin guardar
                # el cuerpo entero. El `async with` garantiza que la conexión se
                # cierre o vuelva al pool aunque nos cancelen a mitad de camino.
                async with self.cliente.stream('GET', url) as r:
                    async for trozo in r.aiter_bytes():
                        tam += len(trozo)
                        if tam > MAX_BYTES_DESCARGA:
                            raise ValueError(f'supera {MAX_BYTES_DESCARGA} bytes')
                res = {'url': url, 'estado_http': r.status_code, 'bytes': tam}
            except Exception as e:      # CancelledError no es Exception: pasa de largo
                detalle = str(e)
                error = f'{type(e).__name__}: {detalle}' if detalle else type(e).__name__
                res = {'url': url, 'error': error}
            res['tiempo'] = round(time.monotonic() - inicio, 4)
            hechas += 1
            tarea.progreso = round(hechas / len(urls), 3)
            return res

        inicio = time.monotonic()
        if tarea.parametros.get('secuencial'):
            resultados = [await una(u) for u in urls]
        else:
            # TaskGroup (clase 21) y no gather: si nos cancelan, el grupo
            # cancela a TODAS las descargas hijas y espera a que terminen antes
            # de propagar la cancelación. No quedan corrutinas huérfanas.
            async with asyncio.TaskGroup() as tg:
                hijas = [tg.create_task(una(u)) for u in urls]
            resultados = [h.result() for h in hijas]

        # ok = respuesta 2xx/3xx. Un 404 o un 500 SÍ es una respuesta (el
        # servidor contestó), pero no es una descarga exitosa.
        ok = sum(1 for r in resultados if r.get('estado_http', 999) < 400)
        return {
            'tiempo_total': round(time.monotonic() - inicio, 4),
            'suma_de_tiempos': round(sum(r['tiempo'] for r in resultados), 4),
            'ok': ok,
            'errores': len(resultados) - ok,
            'descargas': resultados,
        }

    # ---------------------------------------------------------------
    # hashear: CPU-bound
    # ---------------------------------------------------------------

    async def hashear(self, tarea):
        texto = tarea.parametros['texto']
        total = tarea.parametros['iteraciones']
        modo = self.config.hash_executor
        inicio = time.monotonic()

        if modo == 'ninguno':
            # SOLO para la medición 2: el cálculo entero corre en el hilo del
            # event loop. Mientras dura, la API no responde a nadie.
            h = sha256_iterado(texto.encode(), total)
        else:
            h = texto.encode()
            hechas = 0
            tarea.progreso = 0.0
            while hechas < total:
                n = min(BLOQUE_HASH, total - hechas)
                h = await self._en_executor(sha256_iterado, h, n)
                hechas += n
                tarea.progreso = round(hechas / total, 3)

        return {
            'algoritmo': 'sha256',
            'iteraciones': total,
            'hash': h.hex(),
            'executor': modo,
            'tiempo_calculo': round(time.monotonic() - inicio, 4),
        }

    async def _en_executor(self, fn, *args):
        if self.config.hash_executor == 'thread':
            # Saca el cálculo del hilo del loop, pero por el GIL varios hashes
            # en threads no corren en paralelo entre sí (clase 10).
            return await asyncio.to_thread(fn, *args)
        loop = asyncio.get_running_loop()
        pool = self.pool_cpu
        try:
            return await loop.run_in_executor(pool, fn, *args)
        except BrokenProcessPool:
            # Un proceso hijo murió (OOM, kill -9): el pool queda inservible
            # para siempre. Se recrea para las tareas siguientes y esta falla.
            # Si varias tareas lo ven roto a la vez, solo la primera lo recrea.
            if self.pool_cpu is pool:
                log.error('el pool de procesos se rompio; se recrea')
                await self._crear_pool_cpu()
                pool.shutdown(wait=False, cancel_futures=True)
            raise
