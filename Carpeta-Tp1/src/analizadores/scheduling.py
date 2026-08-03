import time

import agregador
import procfs
import recolector


def recolectar_una_vez(pids):
    filas = []
    for pid in pids:
        try:
            stat = procfs.leer_stat(pid)
            status = procfs.leer_status(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue

        filas.append({
            'pid': pid,
            'comm': stat['comm'],
            'nice': stat['nice'],
            'priority': stat['priority'],
            'policy': procfs.POLITICAS_SCHED.get(stat['policy'], f"?{stat['policy']}"),
            'rt_priority': stat['rt_priority'],
            'cpus_allowed': status.get('Cpus_allowed_list', ''),
            'ctxt_voluntarios': int(status.get('voluntary_ctxt_switches', 0) or 0),
            'ctxt_involuntarios': int(status.get('nonvoluntary_ctxt_switches', 0) or 0),
            'utime': stat['utime'],
            'stime': stat['stime'],
            'session': stat['session'],
            'pgrp': stat['pgrp'],
        })
    return filas


def correr(snapshot, intervalo):
    agregador.ignorar_sigint()
    while True:
        pids = recolector.pids_actuales(snapshot)
        agregador.publicar(snapshot, 'scheduling', recolectar_una_vez(pids))
        time.sleep(intervalo.value)
