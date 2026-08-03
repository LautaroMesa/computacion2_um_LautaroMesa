import os
import queue
import select
import signal
import sys
import termios
import threading
import time
import tty

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

import agregador

TECLAS_VISTA = {
    '1': 'resumen', 'r': 'resumen',
    '2': 'memoria', 'm': 'memoria',
    '3': 'fds', 'f': 'fds',
    '4': 'threads', 't': 'threads',
    '5': 'senales', 's': 'senales',
    '6': 'scheduling', 'p': 'scheduling',
    '7': 'sistema', 'g': 'sistema',
}

ESTADOS_LEGIBLES = {
    'R': 'corriendo', 'S': 'durmiendo', 'D': 'espera no interrumpible',
    'T': 'detenido', 'Z': 'zombie', 'I': 'inactivo',
}


class Estado:
    def __init__(self, config):
        self.vista = 'resumen'
        self.orden = 'cpu'  # cpu | rss | pid
        self.indice = 0
        self.pid_pineado = None
        self.filtro_comando = config['filtro_default'].get('comando', '')
        self.filtro_usuario = config['filtro_default'].get('usuario', '')
        self.modo_entrada = None  # None | 'comando' | 'usuario'
        self.buffer_entrada = ''
        self.mostrar_ayuda = False


def leer_teclado(cola, fd):
    """Corre en un hilo aparte del proceso Display (permitido por la consigna
    solo para esto: entrada de teclado). La terminal YA esta en modo cbreak
    cuando este hilo arranca; el propio hilo no la toca.

    Lee de "fd" (un /dev/tty abierto a mano en correr()), NO de sys.stdin:
    multiprocessing le cierra el stdin heredado a todo proceso hijo y lo
    reemplaza por /dev/null, asi que sys.stdin nunca vería la terminal real.
    """
    while True:
        caracter = os.read(fd, 1).decode(errors='replace')
        if caracter == '\x1b':
            # puede ser un ESC solo, o el inicio de una secuencia de flecha
            # (3 bytes). Un timeout corto distingue entre las dos cosas.
            listos, _, _ = select.select([fd], [], [], 0.05)
            if listos:
                resto = os.read(fd, 2).decode(errors='replace')
                mapa = {'\x1b[A': 'ARRIBA', '\x1b[B': 'ABAJO'}
                cola.put(mapa.get(caracter + resto, 'ESC'))
            else:
                cola.put('ESC')
        else:
            cola.put(caracter)


def construir_filas(snapshot, estado):
    filas = list(snapshot['resumen']['datos'])

    if estado.filtro_comando:
        objetivo = estado.filtro_comando.lower()
        filas = [f for f in filas if objetivo in f['comm'].lower()]
    if estado.filtro_usuario:
        objetivo = estado.filtro_usuario.lower()
        filas = [f for f in filas if objetivo in f['usuario'].lower()]

    # rss_kb se calcula siempre (no solo cuando orden == 'rss') porque la
    # tabla lo muestra como columna sea cual sea el orden activo.
    rss_por_pid = {f['pid']: f.get('VmRSS', 0) for f in snapshot['memoria']['datos']}
    for f in filas:
        f['rss_kb'] = rss_por_pid.get(f['pid'], 0)

    if estado.orden == 'cpu':
        filas.sort(key=lambda f: f['cpu_pct'], reverse=True)
    elif estado.orden == 'pid':
        filas.sort(key=lambda f: f['pid'])
    elif estado.orden == 'rss':
        filas.sort(key=lambda f: f['rss_kb'], reverse=True)

    return filas


def tabla_procesos(filas, pid_sel, max_filas):
    tabla = Table(title='Procesos', expand=True)
    tabla.add_column('PID', justify='right', width=7)
    tabla.add_column('USUARIO', width=10)
    tabla.add_column('S', width=1)
    tabla.add_column('CPU%', justify='right', width=6)
    tabla.add_column('RSS(MB)', justify='right', width=8)
    tabla.add_column('THR', justify='right', width=4)
    tabla.add_column('COMANDO', ratio=1)

    for f in filas[:max_filas]:
        estilo = 'reverse bold' if f['pid'] == pid_sel else ''
        tabla.add_row(
            str(f['pid']), f['usuario'], f['state'],
            f"{f['cpu_pct']:.1f}", f"{f['rss_kb'] / 1024:.1f}",
            str(f['threads']), f['comm'],
            style=estilo,
        )
    return tabla


def _buscar(lista, pid):
    return next((f for f in lista if f['pid'] == pid), None)


def panel_resumen(snapshot, pid_sel):
    fila = _buscar(snapshot['resumen']['datos'], pid_sel)
    if not fila:
        return Panel('proceso no encontrado', title='Detalle - Resumen')
    legible = ESTADOS_LEGIBLES.get(fila['state'], fila['state'])
    texto = (
        f"PID {fila['pid']}   PPID {fila['ppid']}\n"
        f"Usuario: {fila['usuario']} (uid {fila['uid']}, gid {fila['gid']})\n"
        f"Estado: {fila['state']} ({legible})\n"
        f"Threads: {fila['threads']}   CPU%: {fila['cpu_pct']:.1f}\n"
        f"Cmd: {fila['cmdline']}"
    )
    return Panel(texto, title=f"Detalle - Resumen (pid {pid_sel})")


def panel_memoria(snapshot, pid_sel):
    fila = _buscar(snapshot['memoria']['datos'], pid_sel)
    if not fila:
        return Panel('sin datos de memoria todavia', title='Detalle - Memoria')
    seg = fila['segmentos']
    texto = (
        f"VmSize {fila['VmSize']} kB   VmRSS {fila['VmRSS']} kB   VmHWM {fila['VmHWM']} kB\n"
        f"VmData {fila['VmData']} kB   VmStk {fila['VmStk']} kB   "
        f"VmExe {fila['VmExe']} kB   VmLib {fila['VmLib']} kB   VmSwap {fila['VmSwap']} kB\n"
        f"Faults: minor={fila['minflt']}  major={fila['majflt']}\n"
        f"Segmentos (bytes): text={seg['text']} data={seg['data']} heap={seg['heap']} "
        f"stack={seg['stack']} shared={seg['shared']} otro={seg['otro']}"
    )
    return Panel(texto, title=f"Detalle - Memoria (pid {pid_sel})")


def panel_fds(snapshot, pid_sel):
    fila = _buscar(snapshot['fds']['datos'], pid_sel)
    if not fila:
        return Panel('sin datos de FDs todavia', title='Detalle - FDs')
    tabla = Table(box=None)
    tabla.add_column('FD')
    tabla.add_column('Tipo')
    tabla.add_column('Destino')
    for entrada in fila['fds'][:15]:
        tabla.add_row(str(entrada['fd']), entrada['tipo'], entrada['destino'])
    return Panel(tabla, title=f"Detalle - FDs (pid {pid_sel}, {len(fila['fds'])} abiertos)")


def panel_threads(snapshot, pid_sel):
    fila = _buscar(snapshot['threads']['datos'], pid_sel)
    if not fila:
        return Panel('sin datos de threads todavia', title='Detalle - Threads')
    tabla = Table(box=None)
    tabla.add_column('TID')
    tabla.add_column('Nombre')
    tabla.add_column('Estado')
    tabla.add_column('CPU%')
    tabla.add_column('Ctx vol.')
    tabla.add_column('Ctx invol.')
    for t in fila['threads'][:15]:
        tabla.add_row(
            str(t['tid']), t['nombre'], t['state'], f"{t['cpu_pct']:.1f}",
            str(t['ctxt_voluntarios']), str(t['ctxt_involuntarios']),
        )
    return Panel(tabla, title=f"Detalle - Threads (pid {pid_sel}, {len(fila['threads'])} LWPs)")


def panel_senales(snapshot, pid_sel):
    fila = _buscar(snapshot['senales']['datos'], pid_sel)
    if not fila:
        return Panel('sin datos de senales todavia', title='Detalle - Senales')
    campos = ['SigBlk', 'SigIgn', 'SigCgt', 'SigPnd', 'ShdPnd']
    texto = '\n'.join(f"{c}: {', '.join(fila[c]) or '(ninguna)'}" for c in campos)
    return Panel(texto, title=f"Detalle - Senales (pid {pid_sel})")


def panel_scheduling(snapshot, pid_sel):
    fila = _buscar(snapshot['scheduling']['datos'], pid_sel)
    if not fila:
        return Panel('sin datos de scheduling todavia', title='Detalle - Scheduling')
    texto = (
        f"Policy: {fila['policy']}   Nice: {fila['nice']}   "
        f"Priority: {fila['priority']}   RT prio: {fila['rt_priority']}\n"
        f"CPU affinity: {fila['cpus_allowed']}\n"
        f"Ctx switches: voluntarios={fila['ctxt_voluntarios']} "
        f"involuntarios={fila['ctxt_involuntarios']}\n"
        f"utime={fila['utime']} stime={fila['stime']} (jiffies)\n"
        f"Sesion (SID): {fila['session']}   Grupo (PGID): {fila['pgrp']}"
    )
    return Panel(texto, title=f"Detalle - Scheduling (pid {pid_sel})")


def panel_sistema(snapshot):
    datos = snapshot['sistema']['datos']
    if not datos or datos.get('cpu_pct') is None:
        return Panel('recolectando datos globales...', title='Detalle - Sistema')
    cpu = datos['cpu_pct']
    mem = datos['meminfo']

    # Top 3 CPU/memoria se derivan de las vistas resumen y memoria, no de una
    # lectura propia: el analizador Sistema solo agrega contadores globales.
    resumen = snapshot['resumen']['datos']
    rss_por_pid = {f['pid']: f.get('VmRSS', 0) for f in snapshot['memoria']['datos']}
    top_cpu = sorted(resumen, key=lambda f: f['cpu_pct'], reverse=True)[:3]
    top_mem = sorted(resumen, key=lambda f: rss_por_pid.get(f['pid'], 0), reverse=True)[:3]
    texto_top_cpu = ', '.join(f"{f['comm']}({f['pid']}) {f['cpu_pct']:.1f}%" for f in top_cpu) or '-'
    texto_top_mem = ', '.join(
        f"{f['comm']}({f['pid']}) {rss_por_pid.get(f['pid'], 0) // 1024}MB" for f in top_mem
    ) or '-'

    boot = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(datos['btime']))

    texto = (
        f"CPU: user={cpu['user']:.1f}% system={cpu['system']:.1f}% "
        f"idle={cpu['idle']:.1f}% iowait={cpu['iowait']:.1f}%\n"
        f"Load average: {datos['loadavg']['1min']:.2f} "
        f"{datos['loadavg']['5min']:.2f} {datos['loadavg']['15min']:.2f}\n"
        f"Memoria: total={mem['MemTotal'] // 1024}MB libre={mem['MemFree'] // 1024}MB "
        f"buffers={mem['Buffers'] // 1024}MB cached={mem['Cached'] // 1024}MB\n"
        f"Swap: total={mem['SwapTotal'] // 1024}MB libre={mem['SwapFree'] // 1024}MB\n"
        f"Procesos: {datos['procesos_totales']} totales, zombies={datos['zombies']}, "
        f"threads totales={datos['threads_totales']}\n"
        f"Por estado: {datos['procesos_por_estado']}\n"
        f"Boot: {boot}   Uptime: {datos['uptime'] / 3600:.1f} h\n"
        f"Top 3 CPU: {texto_top_cpu}\n"
        f"Top 3 memoria: {texto_top_mem}"
    )
    return Panel(texto, title='Detalle - Sistema')


PANELES_POR_VISTA = {
    'resumen': panel_resumen, 'memoria': panel_memoria, 'fds': panel_fds,
    'threads': panel_threads, 'senales': panel_senales, 'scheduling': panel_scheduling,
}


def panel_detalle(snapshot, estado, pid_sel):
    if estado.vista == 'sistema':
        return panel_sistema(snapshot)
    if pid_sel is None:
        return Panel('no hay procesos que mostrar (revisa los filtros)', title='Detalle')
    return PANELES_POR_VISTA[estado.vista](snapshot, pid_sel)


def panel_ayuda():
    texto = (
        '1-7 o r/m/f/t/s/p/g: cambiar de vista\n'
        '↑ ↓: navegar por la lista de procesos\n'
        'Enter: pin/unpin del proceso seleccionado\n'
        '/: filtrar por nombre de comando\n'
        'u: filtrar por usuario\n'
        'c: alternar orden (CPU% / RSS / PID)\n'
        '+ / -: ajustar el intervalo de la vista activa\n'
        'q: salir limpiamente\n'
        'h / ?: esta ayuda'
    )
    return Panel(texto, title='Ayuda (h/? para volver)')


def barra_estado(estado, intervalos):
    intervalo_actual = intervalos[estado.vista].value
    partes = [f'Vista: {estado.vista} ({intervalo_actual:.1f}s)', f'Orden: {estado.orden}']
    if estado.filtro_comando:
        partes.append(f'filtro-cmd: {estado.filtro_comando}')
    if estado.filtro_usuario:
        partes.append(f'filtro-usuario: {estado.filtro_usuario}')
    if estado.pid_pineado is not None:
        partes.append(f'PIN: pid {estado.pid_pineado}')
    if estado.modo_entrada:
        etiqueta = 'comando' if estado.modo_entrada == 'comando' else 'usuario'
        partes.append(f'Filtrar por {etiqueta}: {estado.buffer_entrada}_')

    ayuda = '1-7/rmftspg vistas · ↑↓ navegar · Enter pin · / filtro-cmd · ' \
            'u filtro-usuario · c orden · +/- intervalo · h ayuda · q salir'
    return Panel(' | '.join(partes) + '\n' + ayuda, title='Estado')


def render(snapshot, estado, intervalos, altura_consola):
    if estado.mostrar_ayuda:
        return panel_ayuda()

    filas = construir_filas(snapshot, estado)
    if filas:
        estado.indice = max(0, min(estado.indice, len(filas) - 1))
        if estado.pid_pineado is not None and any(f['pid'] == estado.pid_pineado for f in filas):
            pid_sel = estado.pid_pineado
        else:
            pid_sel = filas[estado.indice]['pid']
    else:
        pid_sel = None

    # La tabla de procesos es la parte de altura VARIABLE de la pantalla; el
    # panel de detalle y la barra de estado son angostos pero fijos. Si la
    # tabla se queda con filas fijas (ej. 20) sin mirar el tamano real de la
    # terminal, en una terminal chica el panel de Estado (con el pin, los
    # filtros y la ayuda de teclas) queda cortado fuera de la pantalla sin
    # ningun aviso - lo vimos pasar en las pruebas con una terminal de 24
    # filas. 16 es una estimacion conservadora de lo que ocupan el panel de
    # detalle + la barra de estado + los bordes/titulo de esta tabla.
    max_filas = max(3, min(20, altura_consola - 16))

    return Group(
        tabla_procesos(filas, pid_sel, max_filas),
        panel_detalle(snapshot, estado, pid_sel),
        barra_estado(estado, intervalos),
    )


def _ajustar_intervalo(intervalos, config, vista, direccion):
    minimo = config['intervalos_minimos'][vista]
    valor = intervalos[vista]
    with valor.get_lock():
        valor.value = max(minimo, valor.value + direccion * 0.5)


def procesar_tecla(tecla, estado, intervalos, config, snapshot):
    if estado.modo_entrada:
        if tecla in ('\r', '\n'):
            if estado.modo_entrada == 'comando':
                estado.filtro_comando = estado.buffer_entrada
            else:
                estado.filtro_usuario = estado.buffer_entrada
            estado.modo_entrada = None
            estado.buffer_entrada = ''
        elif tecla == 'ESC':
            estado.modo_entrada = None
            estado.buffer_entrada = ''
        elif tecla in ('\x7f', '\x08'):
            estado.buffer_entrada = estado.buffer_entrada[:-1]
        elif len(tecla) == 1 and tecla.isprintable():
            estado.buffer_entrada += tecla
        return

    if tecla in TECLAS_VISTA:
        estado.vista = TECLAS_VISTA[tecla]
    elif tecla == 'ARRIBA':
        estado.indice = max(0, estado.indice - 1)
    elif tecla == 'ABAJO':
        estado.indice += 1
    elif tecla in ('\r', '\n'):
        filas = construir_filas(snapshot, estado)
        if filas:
            idx = max(0, min(estado.indice, len(filas) - 1))
            pid_actual = filas[idx]['pid']
            estado.pid_pineado = None if estado.pid_pineado == pid_actual else pid_actual
    elif tecla == '/':
        estado.modo_entrada = 'comando'
        estado.buffer_entrada = ''
    elif tecla == 'u':
        estado.modo_entrada = 'usuario'
        estado.buffer_entrada = ''
    elif tecla == 'c':
        estado.orden = {'cpu': 'rss', 'rss': 'pid', 'pid': 'cpu'}[estado.orden]
    elif tecla == '+':
        _ajustar_intervalo(intervalos, config, estado.vista, 1)
    elif tecla == '-':
        _ajustar_intervalo(intervalos, config, estado.vista, -1)
    elif tecla in ('h', '?'):
        estado.mostrar_ayuda = not estado.mostrar_ayuda
    elif tecla == 'q':
        # Display no se mata a si mismo: le avisa al proceso PADRE (el
        # orquestador) via SIGINT, y este dispara el shutdown limpio de
        # TODOS los componentes por el mismo camino que un Ctrl+C real.
        os.kill(os.getppid(), signal.SIGINT)


def correr(snapshot, intervalos, config):
    agregador.ignorar_sigint()

    try:
        # OJO: no usamos sys.stdin. multiprocessing le cierra el stdin
        # heredado a TODO proceso hijo y lo reemplaza por /dev/null (para que
        # los hijos no compitan por leer del mismo teclado que el padre "por
        # las dudas"), asi que sys.stdin.fileno() en este proceso jamas ve la
        # terminal real, aunque el contenedor si tenga una. /dev/tty es el
        # nombre especial de Unix para "la terminal de control de ESTE
        # proceso", y a diferencia de stdin, multiprocessing no lo toca.
        fd = os.open('/dev/tty', os.O_RDWR)
    except OSError:
        # Pasa si el contenedor corre sin ninguna terminal de verdad (ej.
        # "docker compose up -d"). El resto del monitor (analizadores,
        # senales) sigue funcionando igual; el unico que la necesita es este
        # proceso.
        print('[display] no hay terminal de control (/dev/tty): el monitor '
              'necesita correr en primer plano y con "docker run -it" / '
              '"docker compose run" para mostrar la TUI.')
        return

    config_tty_original = termios.tcgetattr(fd)

    def restaurar_terminal(*_args):
        termios.tcsetattr(fd, termios.TCSADRAIN, config_tty_original)
        sys.exit(0)

    # SIGTERM (lo que manda Process.terminate()) por default mata el proceso
    # sin correr ningun cleanup. Si no capturamos esto, la terminal del host
    # queda trabada en modo cbreak despues de cerrar el monitor.
    signal.signal(signal.SIGTERM, restaurar_terminal)

    estado = Estado(config)
    cola = queue.Queue()

    try:
        tty.setcbreak(fd)
        threading.Thread(target=leer_teclado, args=(cola, fd), daemon=True).start()

        console = Console()
        with Live(console=console, screen=True, auto_refresh=False) as live:
            ultimo_render = 0.0
            while True:
                hubo_tecla = False
                try:
                    tecla = cola.get(timeout=0.2)
                    procesar_tecla(tecla, estado, intervalos, config, snapshot)
                    hubo_tecla = True
                except queue.Empty:
                    pass

                # Redibujar la pantalla completa en CADA vuelta del loop (5
                # veces/seg) titila sobre una terminal remota, sobre todo si
                # nada cambio. Repintamos al toque tras una tecla, pero si no
                # hay tecla nos alcanza con 2 veces/seg (los datos del
                # snapshot cambian mucho mas lento que eso de cualquier forma).
                ahora = time.time()
                if hubo_tecla or ahora - ultimo_render >= 0.5:
                    live.update(
                        render(snapshot, estado, intervalos, console.size.height),
                        refresh=True,
                    )
                    ultimo_render = ahora
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, config_tty_original)
