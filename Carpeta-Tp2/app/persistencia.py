"""Persistencia mínima: volcado del estado a JSON al apagar.

El estado vive en memoria (no hay base de datos, por consigna). Al apagar se
escribe estado_<timestamp>.json; al arrancar se informa el último volcado.
"""
import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger('tp2.persistencia')

PATRON = 'estado_*.json'


def volcar(registro, directorio: Path, extra=None) -> Path:
    """Escribe todas las tareas a estado_<timestamp>.json y devuelve la ruta.

    Se escribe primero a un .tmp y después se renombra: os.replace es atómico,
    así que si el proceso muere a mitad de la escritura nunca queda un
    estado_*.json a medio escribir (queda, como mucho, un .tmp huérfano).
    """
    directorio.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    ruta = directorio / f'estado_{ahora:%Y%m%d_%H%M%S}.json'
    contenido = {
        'version': 1,
        'volcado': ahora.isoformat(),
        'resumen': registro.contar_por_estado(),
        **(extra or {}),
        'tareas': [t.a_dict() for t in registro.listar()],
    }
    tmp = ruta.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, ruta)
    return ruta


def ultimo_volcado(directorio: Path):
    """El volcado más reciente, o None. El nombre lleva la fecha, así que
    ordenar por nombre es ordenar por fecha."""
    if not directorio.is_dir():
        return None
    volcados = sorted(directorio.glob(PATRON))
    return volcados[-1] if volcados else None


def reportar_volcado_previo(directorio: Path):
    """Al arrancar: si hay un volcado previo, decir qué había adentro."""
    ruta = ultimo_volcado(directorio)
    if ruta is None:
        log.info('no hay volcados previos en %s', directorio)
        return None
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        log.warning('volcado previo %s ilegible: %s', ruta.name, e)
        return None
    tareas = datos.get('tareas', [])
    resumen = Counter(t.get('estado') for t in tareas)
    log.info('volcado previo encontrado: %s (del %s), %d tareas: %s',
             ruta.name, datos.get('volcado', '?'), len(tareas),
             ', '.join(f'{n} {e}' for e, n in sorted(resumen.items())) or 'ninguna')
    sin_terminar = resumen.get('pendiente', 0)
    if sin_terminar:
        log.info('  %d tareas quedaron pendientes sin ejecutar en el apagado anterior',
                 sin_terminar)
    return datos
