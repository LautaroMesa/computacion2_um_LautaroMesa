import time

import agregador
import procfs
import recolector


def recolectar_una_vez(pids):
    filas = []
    for pid in pids:
        try:
            stat = procfs.leer_stat(pid)
            lista_fds = procfs.listar_fds(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue

        filas.append({'pid': pid, 'comm': stat['comm'], 'fds': lista_fds})
    return filas


def correr(snapshot, intervalo):
    agregador.ignorar_sigint()
    while True:
        pids = recolector.pids_actuales(snapshot)
        agregador.publicar(snapshot, 'fds', recolectar_una_vez(pids))
        time.sleep(intervalo.value)
