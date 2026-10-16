"""Registro en memoria de todas las tareas y sus transiciones de estado.

Nada de esto necesita Lock: todo corre en el mismo hilo (el del event loop),
y ninguna de estas funciones tiene un `await` adentro. Una vez que una
corrutina entra a, por ejemplo, `marcar_completada`, nadie más puede
ejecutar código hasta que termine (concurrencia cooperativa, clase 18). Los
procesos del executor nunca tocan el registro: solo reciben bytes y
devuelven bytes.
"""
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .modelos import TERMINALES, Estado

# Transiciones válidas. Cualquier otra es un bug y se rechaza.
TRANSICIONES = {
    Estado.PENDIENTE: {Estado.EJECUTANDO, Estado.CANCELADA},
    Estado.EJECUTANDO: {Estado.COMPLETADA, Estado.FALLIDA, Estado.CANCELADA},
}


class TransicionInvalida(Exception):
    pass


def _ahora():
    return datetime.now(timezone.utc)


@dataclass
class Tarea:
    id: int
    tipo: str
    parametros: dict[str, Any]
    timeout: float
    estado: Estado = Estado.PENDIENTE
    creada: datetime = field(default_factory=_ahora)
    iniciada: datetime | None = None
    terminada: datetime | None = None
    worker: int | None = None
    progreso: float | None = None
    resultado: Any = None
    error: str | None = None
    # Lo que sigue es estado interno, no se expone ni se vuelca a JSON
    handle: asyncio.Task | None = field(default=None, repr=False)
    motivo_cancelacion: str | None = field(default=None, repr=False)
    _t_inicio: float | None = field(default=None, repr=False)
    _t_fin: float | None = field(default=None, repr=False)

    @property
    def duracion(self):
        """Segundos de ejecución (medidos con reloj monotónico)."""
        if self._t_inicio is None:
            return None
        fin = self._t_fin if self._t_fin is not None else time.monotonic()
        return round(fin - self._t_inicio, 4)

    @property
    def espera_en_cola(self):
        if self.iniciada is None:
            return None
        return (self.iniciada - self.creada).total_seconds()

    def a_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'estado': self.estado.value,
            'parametros': self.parametros,
            'timeout': self.timeout,
            'creada': self.creada.isoformat(),
            'iniciada': self.iniciada.isoformat() if self.iniciada else None,
            'terminada': self.terminada.isoformat() if self.terminada else None,
            'duracion': self.duracion,
            'progreso': self.progreso,
            'worker': self.worker,
            'resultado': self.resultado,
            'error': self.error,
        }


class Registro:
    def __init__(self):
        self._tareas: dict[int, Tarea] = {}
        self._proximo_id = 0
        self._oyentes: set[asyncio.Queue] = set()

    # --- consultas ---

    def obtener(self, tarea_id):
        return self._tareas.get(tarea_id)

    def listar(self, estado=None):
        tareas = self._tareas.values()
        if estado is not None:
            tareas = (t for t in tareas if t.estado == estado)
        return list(tareas)

    def __len__(self):
        return len(self._tareas)

    def contar_por_estado(self):
        conteo = {e.value: 0 for e in Estado}
        for t in self._tareas.values():
            conteo[t.estado.value] += 1
        return conteo

    def promedios(self):
        """Tiempo medio de ejecución por tipo (de las completadas) y de espera en cola."""
        por_tipo = {}
        for tipo in ('descargar', 'hashear', 'esperar'):
            durs = [t.duracion for t in self._tareas.values()
                    if t.tipo == tipo and t.estado == Estado.COMPLETADA]
            por_tipo[tipo] = round(sum(durs) / len(durs), 4) if durs else None
        esperas = [t.espera_en_cola for t in self._tareas.values() if t.iniciada]
        en_cola = round(sum(esperas) / len(esperas), 4) if esperas else None
        return por_tipo, en_cola

    # --- altas y transiciones ---

    def crear(self, tipo, parametros, timeout):
        self._proximo_id += 1
        tarea = Tarea(id=self._proximo_id, tipo=tipo, parametros=parametros, timeout=timeout)
        self._tareas[tarea.id] = tarea
        self._notificar(tarea)
        return tarea

    def descartar(self, tarea):
        """Saca una tarea que nunca llegó a encolarse (cola llena)."""
        self._tareas.pop(tarea.id, None)

    def _transicion(self, tarea, nuevo):
        if nuevo not in TRANSICIONES.get(tarea.estado, set()):
            raise TransicionInvalida(f'tarea {tarea.id}: {tarea.estado.value} -> {nuevo.value}')
        tarea.estado = nuevo
        if nuevo in TERMINALES:
            tarea.terminada = _ahora()
            if tarea._t_inicio is not None:
                tarea._t_fin = time.monotonic()
        self._notificar(tarea)

    def marcar_ejecutando(self, tarea, worker):
        tarea.iniciada = _ahora()
        tarea._t_inicio = time.monotonic()
        tarea.worker = worker
        self._transicion(tarea, Estado.EJECUTANDO)

    def marcar_completada(self, tarea, resultado):
        tarea.resultado = resultado
        tarea.progreso = 1.0 if tarea.progreso is not None else None
        self._transicion(tarea, Estado.COMPLETADA)

    def marcar_fallida(self, tarea, error):
        tarea.error = error
        self._transicion(tarea, Estado.FALLIDA)

    def marcar_cancelada(self, tarea, motivo):
        tarea.error = motivo
        self._transicion(tarea, Estado.CANCELADA)

    # --- suscripción a cambios (para el WebSocket /eventos) ---

    def suscribir(self, capacidad=1000):
        """Una cola por suscriptor: _notificar le deja cada cambio de estado.

        Es el patrón productor-consumidor otra vez, pero al revés que el pool:
        un productor (el registro) y muchos consumidores (los WebSockets).
        """
        cola = asyncio.Queue(maxsize=capacidad)
        self._oyentes.add(cola)
        return cola

    def desuscribir(self, cola):
        self._oyentes.discard(cola)

    def _notificar(self, tarea):
        if not self._oyentes:
            return
        evento = {'id': tarea.id, 'tipo': tarea.tipo, 'estado': tarea.estado.value,
                  'error': tarea.error, 'momento': _ahora().isoformat()}
        for cola in list(self._oyentes):
            try:
                cola.put_nowait(evento)
            except asyncio.QueueFull:
                # Un cliente que no lee no puede frenar al resto ni hacer
                # crecer la memoria: se vacía su cola, se le deja CORTE y se
                # lo da de baja. El WebSocket, al ver CORTE, cierra la conexión.
                while not cola.empty():
                    cola.get_nowait()
                cola.put_nowait(CORTE)
                self._oyentes.discard(cola)


CORTE = object()     # marca para un suscriptor que se quedó atrás
