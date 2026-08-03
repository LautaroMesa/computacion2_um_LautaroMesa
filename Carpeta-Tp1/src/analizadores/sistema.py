import time

import agregador
import procfs
import recolector


def calcular_cpu_global_pct(actual, previo):
    if previo is None:
        return None
    deltas = {k: actual[k] - previo[k] for k in actual}
    total = sum(deltas.values())
    if total <= 0:
        return {k: 0.0 for k in deltas}
    return {k: (v / total) * 100 for k, v in deltas.items()}


def recolectar_una_vez(pids, cpu_previo):
    stat_global = procfs.leer_stat_global()
    cpu_pct = calcular_cpu_global_pct(stat_global['cpu'], cpu_previo)

    conteo_estados = {}
    threads_totales = 0
    zombies = 0
    for pid in pids:
        try:
            stat = procfs.leer_stat(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        conteo_estados[stat['state']] = conteo_estados.get(stat['state'], 0) + 1
        threads_totales += stat['num_threads']
        if stat['state'] == 'Z':
            zombies += 1

    datos = {
        'cpu_pct': cpu_pct,
        'loadavg': procfs.leer_loadavg(),
        'meminfo': procfs.leer_meminfo(),
        'procesos_totales': sum(conteo_estados.values()),
        'procesos_por_estado': conteo_estados,
        'threads_totales': threads_totales,
        'zombies': zombies,
        'btime': stat_global['btime'],
        'uptime': procfs.leer_uptime(),
    }
    return datos, stat_global['cpu']


def correr(snapshot, intervalo):
    agregador.ignorar_sigint()
    cpu_previo = None
    while True:
        pids = recolector.pids_actuales(snapshot)
        datos, cpu_previo = recolectar_una_vez(pids, cpu_previo)
        agregador.publicar(snapshot, 'sistema', datos)
        time.sleep(intervalo.value)
