"""API HTTP de la plataforma de tareas (FastAPI).

Uso:
    python -m app.main               # escucha en TP2_HOST:TP2_PUERTO (127.0.0.1:8000)
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response

from .config import Config
from .modelos import TERMINALES, Estadisticas, Estado, TareaNueva, TareaOut
from .pool import ColaLlena, NoAcepta, PoolTareas
from .registro import Registro
from .tareas import Ejecutores

log = logging.getLogger('tp2')


def crear_app(config: Config | None = None) -> FastAPI:
    config = config or Config.desde_entorno()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        # Todo lo que vive mientras vive el servidor se crea ACÁ, dentro del
        # event loop que crea uvicorn, y se libera al salir del `yield`.
        registro = Registro()
        ejecutores = Ejecutores(config)
        await ejecutores.abrir()
        pool = PoolTareas(registro, config, ejecutores.como_dict())
        pool.iniciar()
        app.state.registro = registro
        app.state.pool = pool
        try:
            yield
        finally:
            # Orden inverso al de creación: primero los workers (que usan el
            # cliente HTTP y el pool de procesos), después los recursos.
            await pool.apagar(config.gracia_apagado)
            await ejecutores.cerrar()

    app = FastAPI(
        title='TP2 - Plataforma de tareas distribuidas',
        description='Computación II - UM - 2026. Lautaro Mesa.',
        version='1.0.0',
        lifespan=ciclo_de_vida,
    )
    app.state.config = config

    # ---------------------------------------------------------------

    def _registro(request: Request) -> Registro:
        return request.app.state.registro

    def _pool(request: Request) -> PoolTareas:
        return request.app.state.pool

    def _buscar(request, tarea_id):
        tarea = _registro(request).obtener(tarea_id)
        if tarea is None:
            raise HTTPException(404, f'No existe la tarea {tarea_id}')
        return tarea

    @app.get('/')
    async def raiz():
        return {'servicio': 'tp2-tareas', 'docs': '/docs'}

    @app.post('/tareas', response_model=TareaOut, status_code=202,
              responses={503: {'description': 'Cola llena o servidor apagándose'}})
    async def crear_tarea(nueva: TareaNueva, request: Request, response: Response):
        """Encola la tarea y responde en el acto (202 Accepted): NO espera a que se ejecute."""
        registro, pool = _registro(request), _pool(request)
        timeout = nueva.timeout or config.timeout_defecto
        tarea = registro.crear(nueva.tipo, nueva.parametros.model_dump(mode='json'), timeout)
        try:
            pool.encolar(tarea)
        except (ColaLlena, NoAcepta) as e:
            registro.descartar(tarea)
            motivo = ('la cola esta llena' if isinstance(e, ColaLlena)
                      else 'el servidor se esta apagando')
            raise HTTPException(503, f'No se acepta la tarea: {motivo}',
                                headers={'Retry-After': '5'}) from None
        response.headers['Location'] = f'/tareas/{tarea.id}'
        return tarea.a_dict()

    @app.get('/tareas', response_model=list[TareaOut])
    async def listar_tareas(
        request: Request,
        estado: Estado | None = Query(None, description='Filtrar por estado'),
        limite: int = Query(100, ge=1, le=10_000),
    ):
        tareas = _registro(request).listar(estado)
        return [t.a_dict() for t in tareas[-limite:]]

    @app.get('/tareas/{tarea_id}', response_model=TareaOut)
    async def obtener_tarea(tarea_id: int, request: Request):
        return _buscar(request, tarea_id).a_dict()

    @app.delete('/tareas/{tarea_id}', response_model=TareaOut,
                responses={409: {'description': 'La tarea ya terminó'}})
    async def cancelar_tarea(tarea_id: int, request: Request):
        """Cancela una tarea en cola o en ejecución y devuelve su estado final."""
        tarea = _buscar(request, tarea_id)
        if tarea.estado in TERMINALES:
            raise HTTPException(409, f'La tarea {tarea_id} ya termino ({tarea.estado.value})')
        await _pool(request).cancelar(tarea)
        return tarea.a_dict()

    @app.get('/estadisticas', response_model=Estadisticas)
    async def estadisticas(request: Request):
        registro, pool = _registro(request), _pool(request)
        por_tipo, en_cola = registro.promedios()
        return {
            'total': len(registro),
            'por_estado': registro.contar_por_estado(),
            'tiempo_promedio_ejecucion': por_tipo,
            'tiempo_promedio_en_cola': en_cola,
            'workers_total': len(pool.workers),
            'workers_ocupados': pool.ocupados,
            'cola_en_espera': pool.cola.qsize(),
            'cola_capacidad': config.max_cola,
            'aceptando': pool.aceptando,
            'hash_executor': config.hash_executor,
            # Para verificar que la cancelación no deja corrutinas huérfanas:
            # en reposo tiene que volver siempre al mismo número.
            'corrutinas_vivas': len(asyncio.all_tasks()),
        }

    return app


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s')
    config = Config.desde_entorno()
    uvicorn.run(crear_app(config), host=config.host, port=config.puerto)


# La guarda es obligatoria: con 'spawn' (Windows/macOS, y el que usamos para el
# ProcessPoolExecutor) cada proceso hijo re-importa este módulo. Sin ella,
# cada hijo levantaría otro servidor.
if __name__ == '__main__':
    main()
