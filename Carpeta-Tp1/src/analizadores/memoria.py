import time

import agregador
import procfs
import recolector

CAMPOS_VM = ['VmSize', 'VmRSS', 'VmHWM', 'VmData', 'VmStk', 'VmExe', 'VmLib', 'VmSwap']


def recolectar_una_vez(pids):
    filas = []
    for pid in pids:
        try:
            status = procfs.leer_status(pid)
            stat = procfs.leer_stat(pid)
            segmentos = procfs.leer_maps(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            # el proceso murio entre listar_pids() y estas lecturas, o no
            # tenemos permiso (ej: procesos de otro usuario) -> lo salteamos
            continue

        fila = {'pid': pid, 'comm': stat['comm']}
        for campo in CAMPOS_VM:
            fila[campo] = procfs.kb(status.get(campo, ''))
        fila['minflt'] = stat['minflt']
        fila['majflt'] = stat['majflt']
        fila['segmentos'] = segmentos
        filas.append(fila)
    return filas


def correr(snapshot, intervalo):
    agregador.ignorar_sigint()
    while True:
        pids = recolector.pids_actuales(snapshot)
        agregador.publicar(snapshot, 'memoria', recolectar_una_vez(pids))
        time.sleep(intervalo.value)
