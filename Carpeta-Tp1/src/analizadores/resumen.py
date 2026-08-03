import pwd
import time

import agregador
import procfs
import recolector


def _usuario_de(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def recolectar_una_vez(pids, estado_previo):
    ahora = time.time()
    filas = []

    for pid in pids:
        try:
            stat = procfs.leer_stat(pid)
            status = procfs.leer_status(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            # El proceso murio entre que el Recolector listo /proc y esta
            # lectura, o no tenemos permiso: normal, no es un error.
            continue

        jiffies = stat['utime'] + stat['stime']
        previo = estado_previo.get(pid)
        jiffies_previos, ts_previo = previo if previo else (None, None)
        segundos = (ahora - ts_previo) if ts_previo else 0

        cpu_pct = procfs.calcular_cpu_pct(jiffies, jiffies_previos, segundos)
        uid = int(status.get('Uid', '0').split()[0])
        gid = int(status.get('Gid', '0').split()[0])

        filas.append({
            'pid': pid,
            'comm': stat['comm'],
            'cmdline': procfs.leer_cmdline(pid) or f"[{stat['comm']}]",
            'state': stat['state'],
            'ppid': stat['ppid'],
            'uid': uid,
            'gid': gid,
            'usuario': _usuario_de(uid),
            'threads': stat['num_threads'],
            'cpu_pct': cpu_pct,
        })

        estado_previo[pid] = (jiffies, ahora)

    return filas


def correr(snapshot, intervalo):
    """Loop del analizador Resumen: corre en su PROPIO proceso.

    intervalo es un multiprocessing.Value('d', ...) compartido con el Display,
    para que +/- pueda cambiar el ritmo de refresco en caliente.
    """
    agregador.ignorar_sigint()
    estado_previo = {}
    while True:
        pids = recolector.pids_actuales(snapshot)
        filas = recolectar_una_vez(pids, estado_previo)
        filas.sort(key=lambda f: f['cpu_pct'], reverse=True)
        agregador.publicar(snapshot, 'resumen', filas)
        time.sleep(intervalo.value)
