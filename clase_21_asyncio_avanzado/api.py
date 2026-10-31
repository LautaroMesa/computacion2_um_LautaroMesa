#!/usr/bin/env python3
"""API de tareas de la clase 19, con POST /hashear (clase 21, ejercicio 3D).

Clase 21:
  - POST  /hashear?modo=directo    el calculo pesado DENTRO del loop (lo bloquea)
  - POST  /hashear?modo=executor   el mismo calculo en un ProcessPoolExecutor
                                   creado una sola vez en el lifespan

De la clase 19 (ejercicio 3):
  - PATCH /tareas/{id}     cambia solo el estado (modelo con todo opcional)
  - GET   /estadisticas    cantidad de tareas por estado
  - POST  /tareas          rechaza con 503 si ya hay MAX_PENDIENTES pendientes
  - un print en crear() para ver que la validacion corre ANTES de la funcion

Uso:
    pip install -r requirements.txt
    python3 api.py                   # http://localhost:8000/docs
"""
import asyncio
import hashlib
import os
import threading
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

VUELTAS = int(os.environ.get('VUELTAS', 3_000_000))   # ~3-5 s de CPU


def hashear(vueltas: int = VUELTAS) -> str:
    """CPU-bound puro, a nivel modulo para que el pool lo pueda picklear."""
    h = b'x'
    for _ in range(vueltas):
        h = hashlib.sha256(h).digest()
    return h.hex()[:16]


@asynccontextmanager
async def ciclo(app: FastAPI):
    # El pool se crea UNA vez al arrancar: crear procesos cuesta (parte C).
    app.state.pool = ProcessPoolExecutor(max_workers=2)
    yield
    app.state.pool.shutdown(cancel_futures=True)


app = FastAPI(
    title='Tareas',
    description='Clase 19/21: API de tareas con un endpoint CPU-bound',
    lifespan=ciclo,
)

Estado = Literal['pendiente', 'ejecutando', 'completada']
MAX_PENDIENTES = 10

# Estado en memoria. OJO: con --workers > 1 cada proceso tiene el suyo.
tareas: dict[int, dict] = {}
proximo_id = 0


# ---------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------

class TareaNueva(BaseModel):
    """Lo que el cliente manda en el cuerpo de un POST."""
    tipo: Literal['descargar', 'hashear', 'esperar']
    prioridad: int = Field(default=1, ge=1, le=5,
                           description='1 = mas baja, 5 = mas alta')


class Tarea(TareaNueva):
    """Lo que devolvemos: lo anterior mas lo que agrega el servidor."""
    id: int
    estado: Estado = 'pendiente'


class TareaCambios(BaseModel):
    """Cuerpo de un PATCH: todos los campos opcionales.

    La consigna pide cambiar solo el estado, pero lo dejo preparado para
    cambiar tambien la prioridad: en un PATCH solo se tocan los campos que
    vienen en el cuerpo (exclude_unset), el resto queda como estaba.
    """
    estado: Estado | None = None
    prioridad: int | None = Field(default=None, ge=1, le=5)


class Estadisticas(BaseModel):
    total: int
    por_estado: dict[str, int]


# ---------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------

@app.get('/')
async def raiz():
    return {'servicio': 'tareas', 'docs': '/docs'}


@app.get('/tareas', response_model=list[Tarea])
async def listar(
    estado: Estado | None = Query(default=None, description='Filtrar por estado'),
    limite: int = Query(default=10, ge=1, le=100),
):
    items = list(tareas.values())
    if estado:
        items = [t for t in items if t['estado'] == estado]
    return items[:limite]


@app.post('/tareas', response_model=Tarea, status_code=201,
          responses={503: {'description': 'Cola llena: demasiadas tareas pendientes'}})
async def crear(nueva: TareaNueva):
    # Si este print aparece, el cuerpo YA paso la validacion: con un cuerpo
    # invalido FastAPI responde 422 sin llegar a llamar a esta funcion.
    print(f'crear() ejecutandose con {nueva!r}', flush=True)

    pendientes = sum(1 for t in tareas.values() if t['estado'] == 'pendiente')
    if pendientes >= MAX_PENDIENTES:
        raise HTTPException(
            status_code=503,
            detail=f'Hay {pendientes} tareas pendientes (maximo {MAX_PENDIENTES}); '
                   'reintentar mas tarde',
            headers={'Retry-After': '5'},
        )

    global proximo_id
    proximo_id += 1
    tarea = {'id': proximo_id, **nueva.model_dump(), 'estado': 'pendiente'}
    tareas[proximo_id] = tarea
    return tarea


@app.get('/tareas/{tarea_id}', response_model=Tarea)
async def obtener(tarea_id: int):
    if tarea_id not in tareas:
        raise HTTPException(status_code=404, detail='No existe esa tarea')
    return tareas[tarea_id]


@app.patch('/tareas/{tarea_id}', response_model=Tarea)
async def modificar(tarea_id: int, cambios: TareaCambios):
    if tarea_id not in tareas:
        raise HTTPException(status_code=404, detail='No existe esa tarea')
    # exclude_unset: solo los campos que el cliente mando de verdad. Sin esto,
    # un PATCH con {"estado": ...} pisaria la prioridad con None.
    tareas[tarea_id].update(cambios.model_dump(exclude_unset=True))
    return tareas[tarea_id]


@app.delete('/tareas/{tarea_id}', status_code=204)
async def borrar(tarea_id: int):
    if tarea_id not in tareas:
        raise HTTPException(status_code=404, detail='No existe esa tarea')
    del tareas[tarea_id]


@app.get('/estadisticas', response_model=Estadisticas)
async def estadisticas():
    conteo = Counter(t['estado'] for t in tareas.values())
    # los tres estados siempre presentes, aunque tengan 0
    por_estado = {e: conteo.get(e, 0) for e in ('pendiente', 'ejecutando', 'completada')}
    return {'total': len(tareas), 'por_estado': por_estado}


@app.post('/hashear')
async def hashear_endpoint(modo: Literal['directo', 'executor'] = 'executor'):
    t0 = time.perf_counter()
    if modo == 'directo':
        resultado = hashear()          # congela el event loop todo el calculo
    else:
        loop = asyncio.get_running_loop()
        resultado = await loop.run_in_executor(app.state.pool, hashear)
    return {'modo': modo, 'hash': resultado,
            'segundos': round(time.perf_counter() - t0, 2)}


@app.get('/quien-soy')
async def quien_soy():
    loop = asyncio.get_running_loop()
    return {
        'pid': os.getpid(),
        'thread': threading.current_thread().name,
        'loop': type(loop).__name__,
        'id_del_loop': id(loop),
    }


@app.get('/quien-soy-sync')
def quien_soy_sync():
    try:
        asyncio.get_running_loop()
        estado = 'HAY loop'
    except RuntimeError:
        estado = 'NO hay loop corriendo aca'
    return {'thread': threading.current_thread().name, 'loop': estado}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=os.environ.get('HOST', '127.0.0.1'), port=8000)
