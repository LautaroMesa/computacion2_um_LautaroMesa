"""Pool de workers: N corrutinas que consumen una asyncio.Queue.

Es el productor-consumidor de la clase 11 con corrutinas en vez de threads.
El productor es el endpoint POST /tareas (pone el id en la cola y vuelve en
el acto); los consumidores son los workers.

Cada tarea se ejecuta en su PROPIO asyncio.Task (el "job"), separado del
worker que la tomó. Eso permite cancelar una tarea en ejecución
(DELETE /tareas/{id} -> job.cancel()) sin matar al worker: el worker ve que
el job terminó cancelado, lo anota y vuelve a la cola.
"""
import asyncio
import logging

from .modelos import Estado

log = logging.getLogger('tp2.pool')

CENTINELA = object()     # "no hay más trabajo": un worker que lo saca, termina


class ColaLlena(Exception):
    pass


class NoAcepta(Exception):
    pass


class PoolTareas:
    def __init__(self, registro, config, ejecutores):
        """ejecutores: {tipo: corrutina(tarea) -> resultado}."""
        self.registro = registro
        self.config = config
        self.ejecutores = ejecutores
        self.cola = asyncio.Queue(maxsize=config.max_cola)
        self.workers: list[asyncio.Task] = []
        self.ocupados = 0
        self.aceptando = True
        self._apagando = False

    # ---------------------------------------------------------------
    # ciclo de vida
    # ---------------------------------------------------------------

    def iniciar(self):
        for i in range(self.config.workers):
            self._lanzar_worker(i)
        log.info('pool iniciado: %d workers, cola de %d', self.config.workers, self.config.max_cola)

    def _lanzar_worker(self, i):
        w = asyncio.create_task(self._worker(i), name=f'worker-{i}')
        w.add_done_callback(lambda t, i=i: self._worker_terminado(t, i))
        if i < len(self.workers):
            self.workers[i] = w
        else:
            self.workers.append(w)

    def _worker_terminado(self, w, i):
        """Red de seguridad: un worker solo debería terminar al apagar.

        _ejecutar ya convierte cualquier excepción de una tarea en
        estado 'fallida', así que llegar acá con una excepción significa un
        bug en el propio worker. En vez de perder silenciosamente un worker
        (y con el tiempo quedarse sin ninguno), se loguea y se relanza.
        """
        if self._apagando or w.cancelled():
            return
        exc = w.exception()
        if exc is not None:
            log.error('worker-%d murio con %r; se relanza', i, exc)
            self._lanzar_worker(i)

    async def apagar(self, gracia):
        """Apagado ordenado: no aceptar más, esperar (con límite) a las que
        están en curso, cancelar las que no llegaron y frenar los workers."""
        self.aceptando = False
        self._apagando = True
        en_curso = [t.handle for t in self.registro.listar(Estado.EJECUTANDO) if t.handle]
        if en_curso:
            log.info('apagado: esperando hasta %.1fs a %d tareas en curso', gracia, len(en_curso))
            _, pendientes = await asyncio.wait(en_curso, timeout=gracia)
            for job in pendientes:
                self._tarea_de(job).motivo_cancelacion = 'apagado del servidor (venció la gracia)'
                job.cancel()
            if pendientes:
                log.warning('apagado: %d tareas no terminaron a tiempo, se cancelan', len(pendientes))
        for w in self.workers:
            w.cancel()
        # gather con return_exceptions: esperar a que TODOS terminen de
        # cancelarse (que corran sus finally) sin que uno corte a los demás
        await asyncio.gather(*self.workers, return_exceptions=True)
        log.info('pool detenido')

    def _tarea_de(self, job):
        return self.registro.obtener(int(job.get_name().split('-')[1]))

    # ---------------------------------------------------------------
    # productor
    # ---------------------------------------------------------------

    def encolar(self, tarea):
        """Lo llama el POST. No espera nada: o entra a la cola ya, o falla ya."""
        if not self.aceptando:
            raise NoAcepta()
        try:
            self.cola.put_nowait(tarea.id)
        except asyncio.QueueFull:
            raise ColaLlena() from None

    # ---------------------------------------------------------------
    # consumidores
    # ---------------------------------------------------------------

    async def _worker(self, i):
        while True:
            tarea_id = await self.cola.get()
            try:
                if tarea_id is CENTINELA:
                    return
                tarea = self.registro.obtener(tarea_id)
                # Pudo haber sido cancelada mientras esperaba en la cola
                if tarea is None or tarea.estado != Estado.PENDIENTE:
                    continue
                # Al apagar no se arrancan tareas nuevas: quedan 'pendiente' en el volcado
                if self._apagando:
                    continue
                await self._ejecutar(tarea, i)
            finally:
                self.cola.task_done()

    async def _ejecutar(self, tarea, i):
        ejecutor = self.ejecutores.get(tarea.tipo)
        self.registro.marcar_ejecutando(tarea, worker=i)
        self.ocupados += 1
        job = asyncio.create_task(self._correr(ejecutor, tarea), name=f'tarea-{tarea.id}')
        tarea.handle = job
        try:
            resultado = await job
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                # Cancelaron al WORKER (apagado), no solo a la tarea. Al
                # cancelar un Task que espera a otro, asyncio cancela también
                # al de adentro; igual se espera a que termine de limpiar.
                job.cancel()
                await asyncio.gather(job, return_exceptions=True)
                self._anotar_cancelada(tarea, 'apagado del servidor')
                raise
            self._anotar_cancelada(tarea, tarea.motivo_cancelacion or 'cancelada')
        except TimeoutError:
            self.registro.marcar_fallida(tarea, f'timeout: supero los {tarea.timeout:g}s')
        except Exception as e:
            log.warning('tarea %d (%s) fallo: %r', tarea.id, tarea.tipo, e)
            self.registro.marcar_fallida(tarea, f'{type(e).__name__}: {e}')
        else:
            self.registro.marcar_completada(tarea, resultado)
        finally:
            tarea.handle = None
            self.ocupados -= 1

    def _anotar_cancelada(self, tarea, motivo):
        if tarea.estado == Estado.EJECUTANDO:
            self.registro.marcar_cancelada(tarea, motivo)

    async def _correr(self, ejecutor, tarea):
        if ejecutor is None:
            raise NotImplementedError(f'tipo {tarea.tipo!r} sin implementar')
        # asyncio.timeout cancela lo que esté adentro al vencer y lo
        # convierte en TimeoutError (clase 20)
        async with asyncio.timeout(tarea.timeout):
            return await ejecutor(tarea)

    # ---------------------------------------------------------------
    # cancelación pedida por el usuario
    # ---------------------------------------------------------------

    async def cancelar(self, tarea, espera=5.0):
        """Cancela una tarea pendiente o en ejecución.

        Si está en la cola, alcanza con marcarla: el worker que la saque la
        saltea. Si está ejecutándose, se cancela su job; se espera un poco a
        que termine de cancelarse (que corran sus finally, se cierren sus
        conexiones) para devolver el estado final.
        """
        if tarea.estado == Estado.PENDIENTE:
            self.registro.marcar_cancelada(tarea, 'cancelada mientras estaba en la cola')
            return True
        if tarea.estado == Estado.EJECUTANDO and tarea.handle is not None:
            job = tarea.handle
            tarea.motivo_cancelacion = 'cancelada durante la ejecucion'
            job.cancel()
            await asyncio.wait([job], timeout=espera)
            return True
        return False
