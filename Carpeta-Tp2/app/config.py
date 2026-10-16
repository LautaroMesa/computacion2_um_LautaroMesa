"""Configuración del servicio, leída de variables de entorno.

Todo tiene un valor por defecto razonable, así que el servicio arranca sin
configurar nada. En Docker se ajusta desde docker-compose.yml.
"""
import os
from dataclasses import dataclass
from pathlib import Path

MODOS_HASH = ('proceso', 'thread', 'ninguno')


def _entero(nombre, defecto):
    return int(os.environ.get(nombre, defecto))


def _decimal(nombre, defecto):
    return float(os.environ.get(nombre, defecto))


@dataclass(frozen=True)
class Config:
    workers: int = 4                 # corrutinas que consumen la cola
    procesos: int = 2                # procesos del ProcessPoolExecutor (hashear)
    max_cola: int = 1000             # capacidad de la asyncio.Queue
    timeout_defecto: float = 60.0    # segundos, si la tarea no trae el suyo
    timeout_maximo: float = 3600.0
    gracia_apagado: float = 10.0     # cuánto esperar a las tareas en curso al apagar
    dir_estado: Path = Path('estado')
    # Dónde corre hashear: 'proceso' (lo correcto), 'thread', o 'ninguno'
    # (directo en el event loop: SOLO para la medición 2, bloquea la API).
    hash_executor: str = 'proceso'
    max_conexiones: int = 100        # conexiones simultáneas del cliente HTTP
    host: str = '127.0.0.1'
    puerto: int = 8000

    @classmethod
    def desde_entorno(cls):
        modo = os.environ.get('TP2_HASH_EXECUTOR', cls.hash_executor)
        if modo not in MODOS_HASH:
            raise ValueError(f'TP2_HASH_EXECUTOR={modo!r}: tiene que ser uno de {MODOS_HASH}')
        cfg = cls(
            workers=_entero('TP2_WORKERS', cls.workers),
            procesos=_entero('TP2_PROCESOS', cls.procesos),
            max_cola=_entero('TP2_MAX_COLA', cls.max_cola),
            timeout_defecto=_decimal('TP2_TIMEOUT', cls.timeout_defecto),
            timeout_maximo=_decimal('TP2_TIMEOUT_MAXIMO', cls.timeout_maximo),
            gracia_apagado=_decimal('TP2_GRACIA', cls.gracia_apagado),
            dir_estado=Path(os.environ.get('TP2_DIR_ESTADO', cls.dir_estado)),
            hash_executor=modo,
            max_conexiones=_entero('TP2_MAX_CONEXIONES', cls.max_conexiones),
            host=os.environ.get('TP2_HOST', cls.host),
            puerto=_entero('TP2_PUERTO', cls.puerto),
        )
        if cfg.workers < 1 or cfg.procesos < 1 or cfg.max_cola < 1:
            raise ValueError('TP2_WORKERS, TP2_PROCESOS y TP2_MAX_COLA tienen que ser >= 1')
        return cfg
