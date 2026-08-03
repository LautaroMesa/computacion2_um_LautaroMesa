import time

import agregador
import procfs
import recolector

# Nota: este modulo describe las senales PENDIENTES/BLOQUEADAS/etc de cada
# proceso monitoreado (dato que se lee de /proc). No confundir con
# src/senales.py, que maneja las senales que el propio monitor recibe.
CAMPOS_MASCARA = ['SigBlk', 'SigIgn', 'SigCgt', 'SigPnd', 'ShdPnd']


def recolectar_una_vez(pids):
    filas = []
    for pid in pids:
        try:
            stat = procfs.leer_stat(pid)
            status = procfs.leer_status(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue

        fila = {'pid': pid, 'comm': stat['comm']}
        for campo in CAMPOS_MASCARA:
            mascara = status.get(campo, '0')
            fila[campo] = procfs.decodificar_mascara_senales(mascara)
        filas.append(fila)
    return filas


def correr(snapshot, intervalo):
    agregador.ignorar_sigint()
    while True:
        pids = recolector.pids_actuales(snapshot)
        agregador.publicar(snapshot, 'senales', recolectar_una_vez(pids))
        time.sleep(intervalo.value)
