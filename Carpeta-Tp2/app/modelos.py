"""Modelos de la API: qué se puede pedir y qué se devuelve.

El cuerpo de POST /tareas es una unión discriminada por `tipo`: según el
tipo, Pydantic valida un modelo de `parametros` distinto. Un pedido mal
armado se rechaza con 422 antes de llegar a la cola (clase 19).
"""
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, HttpUrl


class Estado(str, Enum):
    PENDIENTE = 'pendiente'
    EJECUTANDO = 'ejecutando'
    COMPLETADA = 'completada'
    FALLIDA = 'fallida'
    CANCELADA = 'cancelada'


TERMINALES = {Estado.COMPLETADA, Estado.FALLIDA, Estado.CANCELADA}


# ---------------------------------------------------------------
# Parámetros de cada tipo de tarea
# ---------------------------------------------------------------

class ParamsDescargar(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=100)
    secuencial: bool = Field(
        default=False,
        description='Descargar de a una (para comparar contra la versión concurrente)',
    )


class ParamsHashear(BaseModel):
    texto: str = Field(max_length=10_000)
    iteraciones: int = Field(ge=1, le=100_000_000)


class ParamsEsperar(BaseModel):
    segundos: float = Field(ge=0, le=3600)


TimeoutTarea = Annotated[float | None, Field(
    default=None, gt=0, le=3600,
    description='Segundos; si se supera, la tarea pasa a fallida. Por defecto, el del servidor',
)]


class NuevaDescargar(BaseModel):
    tipo: Literal['descargar']
    parametros: ParamsDescargar
    timeout: TimeoutTarea = None


class NuevaHashear(BaseModel):
    tipo: Literal['hashear']
    parametros: ParamsHashear
    timeout: TimeoutTarea = None


class NuevaEsperar(BaseModel):
    tipo: Literal['esperar']
    parametros: ParamsEsperar
    timeout: TimeoutTarea = None


TareaNueva = Annotated[
    Union[NuevaDescargar, NuevaHashear, NuevaEsperar],
    Field(discriminator='tipo'),
]


# ---------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------

class TareaOut(BaseModel):
    id: int
    tipo: str
    estado: Estado
    parametros: dict[str, Any]
    timeout: float
    creada: datetime
    iniciada: datetime | None = None
    terminada: datetime | None = None
    duracion: float | None = Field(None, description='Segundos de ejecución')
    progreso: float | None = Field(None, description='0 a 1, si el tipo lo informa')
    worker: int | None = None
    resultado: Any = None
    error: str | None = None


class Estadisticas(BaseModel):
    total: int
    por_estado: dict[str, int]
    tiempo_promedio_ejecucion: dict[str, float | None]
    tiempo_promedio_en_cola: float | None
    workers_total: int
    workers_ocupados: int
    cola_en_espera: int
    cola_capacidad: int
    aceptando: bool
    hash_executor: str
