import os
import signal

CLOCK_TICKS_PER_SEC = os.sysconf('SC_CLK_TCK')

# Campos de /proc/<pid>/stat a partir del 3ro (los dos primeros, pid y comm,
# se parsean aparte). El orden importa: es el orden real segun man proc(5).
CAMPOS_STAT = [
    'state', 'ppid', 'pgrp', 'session', 'tty_nr', 'tpgid', 'flags',
    'minflt', 'cminflt', 'majflt', 'cmajflt', 'utime', 'stime',
    'cutime', 'cstime', 'priority', 'nice', 'num_threads',
    'itrealvalue', 'starttime', 'vsize', 'rss',
    'rsslim', 'startcode', 'endcode', 'startstack', 'kstkesp', 'kstkeip',
    'signal', 'blocked', 'sigignore', 'sigcatch', 'wchan', 'nswap',
    'cnswap', 'exit_signal', 'processor', 'rt_priority', 'policy',
]

CAMPOS_STAT_INT = set(CAMPOS_STAT) - {'state'}

POLITICAS_SCHED = {
    0: 'OTHER', 1: 'FIFO', 2: 'RR', 3: 'BATCH', 4: 'ISO', 5: 'IDLE', 6: 'DEADLINE',
}


def listar_pids():
    return [int(entry) for entry in os.listdir('/proc') if entry.isdigit()]


def calcular_cpu_pct(jiffies_actuales, jiffies_previos, segundos_transcurridos):
    """CPU% entre dos lecturas de jiffies acumulados (utime+stime).

    Como un odometro: una sola lectura no dice nada, hace falta el delta
    entre dos lecturas separadas en el tiempo.
    """
    if jiffies_previos is None or segundos_transcurridos <= 0:
        return 0.0
    delta_jiffies = jiffies_actuales - jiffies_previos
    return (delta_jiffies / CLOCK_TICKS_PER_SEC / segundos_transcurridos) * 100


def leer_stat(pid, base='/proc'):
    with open(f'{base}/{pid}/stat', 'r') as f:
        contenido = f.read()

    # comm va entre parentesis y puede contener espacios (ej "(kworker/0:1)"),
    # asi que no podemos hacer split() ingenuo: buscamos el ULTIMO ')' porque
    # el nombre en si tambien podria contener parentesis.
    fin_comm = contenido.rindex(')')
    comm = contenido[contenido.index('(') + 1:fin_comm]
    resto = contenido[fin_comm + 2:].split()

    valores = dict(zip(CAMPOS_STAT, resto))
    for campo in CAMPOS_STAT_INT:
        valores[campo] = int(valores[campo])

    valores['pid'] = pid
    valores['comm'] = comm
    return valores


def leer_cmdline(pid, base='/proc'):
    try:
        with open(f'{base}/{pid}/cmdline', 'rb') as f:
            crudo = f.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return ''

    # cmdline separa los argumentos con bytes nulos en vez de espacios
    partes = crudo.split(b'\x00')
    return ' '.join(p.decode(errors='replace') for p in partes if p)


def leer_status(pid, base='/proc'):
    """Parsea /proc/<pid>/status como dict de strings crudos (sin convertir).

    Cada linea tiene forma "Campo:\\tvalor", pero el tipo de "valor" varia
    mucho (numero simple, "1234 kB", lista "0-7", mascara hex de 64 bits),
    asi que la conversion queda en manos de quien consume cada campo.
    """
    campos = {}
    with open(f'{base}/{pid}/status', 'r') as f:
        for linea in f:
            clave, _, valor = linea.partition(':')
            campos[clave.strip()] = valor.strip()
    return campos


def kb(valor_status):
    """Convierte un valor tipo 'VmRSS: 1234 kB' (ya sin la clave) a int."""
    if not valor_status:
        return 0
    return int(valor_status.split()[0])


def leer_maps(pid, base='/proc'):
    """Agrupa /proc/<pid>/maps por tipo de segmento (text/data/heap/stack/shared/otro)."""
    segmentos = {'text': 0, 'data': 0, 'heap': 0, 'stack': 0, 'shared': 0, 'otro': 0}
    with open(f'{base}/{pid}/maps', 'r') as f:
        for linea in f:
            partes = linea.split(maxsplit=5)
            rango, permisos = partes[0], partes[1]
            etiqueta = partes[5].strip() if len(partes) > 5 else ''

            inicio, fin = (int(x, 16) for x in rango.split('-'))
            tamano = fin - inicio

            if 'heap' in etiqueta:
                tipo = 'heap'
            elif 'stack' in etiqueta:
                tipo = 'stack'
            elif permisos[1] == 'w' and 's' in permisos:
                tipo = 'shared'
            elif 'x' in permisos:
                tipo = 'text'
            elif permisos[1] == 'w':
                tipo = 'data'
            else:
                tipo = 'otro'

            segmentos[tipo] += tamano
    return segmentos


def listar_fds(pid, base='/proc'):
    directorio = f'{base}/{pid}/fd'
    resultado = []
    for entry in os.listdir(directorio):
        try:
            destino = os.readlink(f'{directorio}/{entry}')
        except OSError:
            continue
        resultado.append({'fd': int(entry), 'destino': destino, 'tipo': _tipo_fd(destino)})
    return resultado


def _tipo_fd(destino):
    if destino.startswith('socket:'):
        return 'socket'
    if destino.startswith('pipe:'):
        return 'pipe'
    if destino.startswith('/dev/pts') or destino.startswith('/dev/tty'):
        return 'tty'
    if destino.startswith('anon_inode:'):
        return 'anon_inode'
    return 'file'


def listar_threads(pid, base='/proc'):
    """Lista los LWPs (threads) de un proceso.

    Reusa leer_stat() pasando el directorio task/ como "base" y el tid como
    "pid": /proc/<pid>/task/<tid>/stat tiene EXACTAMENTE el mismo formato que
    /proc/<pid>/stat, porque para el kernel un thread tambien es una "task".
    """
    directorio_task = f'{base}/{pid}/task'
    resultado = []
    for entry in os.listdir(directorio_task):
        tid = int(entry)
        try:
            stat = leer_stat(tid, base=directorio_task)
            status = leer_status(tid, base=directorio_task)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue

        try:
            with open(f'{directorio_task}/{tid}/comm', 'r') as f:
                nombre = f.read().strip()
        except FileNotFoundError:
            nombre = stat['comm']

        resultado.append({
            'tid': tid, 'nombre': nombre, 'state': stat['state'],
            'utime': stat['utime'], 'stime': stat['stime'],
            'ctxt_voluntarios': int(status.get('voluntary_ctxt_switches', 0) or 0),
            'ctxt_involuntarios': int(status.get('nonvoluntary_ctxt_switches', 0) or 0),
        })
    return resultado


def decodificar_mascara_senales(mascara_hex):
    """Convierte una mascara como SigBlk ('0000000000000004') a nombres de señal."""
    valor = int(mascara_hex, 16)
    nombres = []
    for bit in range(64):
        if not (valor & (1 << bit)):
            continue
        numero = bit + 1
        try:
            nombres.append(signal.Signals(numero).name)
        except ValueError:
            nombres.append(f'RT{numero}')
    return nombres


def leer_stat_global():
    """Linea 'cpu' agregada y btime de /proc/stat."""
    resultado = {}
    with open('/proc/stat', 'r') as f:
        for linea in f:
            if linea.startswith('cpu '):
                partes = linea.split()
                claves = ['user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal']
                resultado['cpu'] = {k: int(v) for k, v in zip(claves, partes[1:])}
            elif linea.startswith('btime'):
                resultado['btime'] = int(linea.split()[1])
    return resultado


def leer_loadavg():
    with open('/proc/loadavg', 'r') as f:
        partes = f.read().split()
    return {'1min': float(partes[0]), '5min': float(partes[1]), '15min': float(partes[2])}


def leer_meminfo():
    campos = {}
    with open('/proc/meminfo', 'r') as f:
        for linea in f:
            clave, _, valor = linea.partition(':')
            campos[clave.strip()] = kb(valor.strip())
    return campos


def leer_uptime():
    with open('/proc/uptime', 'r') as f:
        segundos, _ = f.read().split()
    return float(segundos)
