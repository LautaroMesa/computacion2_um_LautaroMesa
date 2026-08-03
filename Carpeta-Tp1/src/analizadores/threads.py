import time

import agregador
import procfs
import recolector


def recolectar_una_vez(pids, estado_previo):
    ahora = time.time()
    filas = []

    for pid in pids:
        try:
            stat_proceso = procfs.leer_stat(pid)
            threads = procfs.listar_threads(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue

        lista_threads = []
        for t in threads:
            clave = (pid, t['tid'])
            jiffies = t['utime'] + t['stime']
            previo = estado_previo.get(clave)
            jiffies_previos, ts_previo = previo if previo else (None, None)
            segundos = (ahora - ts_previo) if ts_previo else 0

            lista_threads.append({
                'tid': t['tid'], 'nombre': t['nombre'], 'state': t['state'],
                'cpu_pct': procfs.calcular_cpu_pct(jiffies, jiffies_previos, segundos),
                'ctxt_voluntarios': t['ctxt_voluntarios'],
                'ctxt_involuntarios': t['ctxt_involuntarios'],
            })
            estado_previo[clave] = (jiffies, ahora)

        filas.append({'pid': pid, 'comm': stat_proceso['comm'], 'threads': lista_threads})

    return filas


def correr(snapshot, intervalo):
    agregador.ignorar_sigint()
    estado_previo = {}
    while True:
        pids = recolector.pids_actuales(snapshot)
        agregador.publicar(snapshot, 'threads', recolectar_una_vez(pids, estado_previo))
        time.sleep(intervalo.value)
