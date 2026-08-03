import json
import multiprocessing
import signal
import time

import agregador
import display
import recolector
from senales import ManejadorSenales
from analizadores import fds, memoria, resumen, scheduling, sistema, threads
from analizadores import senales as analizador_senales

ANALIZADORES = {
    'resumen': resumen.correr,
    'memoria': memoria.correr,
    'fds': fds.correr,
    'threads': threads.correr,
    'senales': analizador_senales.correr,
    'scheduling': scheduling.correr,
    'sistema': sistema.correr,
}


def cargar_config(ruta='config.json'):
    with open(ruta, 'r') as f:
        return json.load(f)


def dump_snapshot(snapshot):
    payload = {vista: dict(entrada) for vista, entrada in snapshot.items()}
    nombre = f'dump_{int(time.time())}.json'
    with open(nombre, 'w') as f:
        json.dump(payload, f, indent=2, default=str)
    print(f'[monitor] dump guardado en {nombre}')


def main():
    config = cargar_config()

    manager = multiprocessing.Manager()
    snapshot = agregador.crear_snapshot_inicial(manager)

    intervalos = {
        vista: multiprocessing.Value('d', config['intervalos'][vista])
        for vista in agregador.VISTAS
    }
    verbose = multiprocessing.Value('b', False)

    procesos = {}

    # El Recolector arranca primero y le damos una vuelta de ventaja para
    # que publique la primera lista de PIDs antes de que los analizadores
    # la empiecen a consumir (si la consultan estando vacia, simplemente no
    # publican filas esa vuelta - no rompe nada, pero asi arranca mas fluido).
    procesos['recolector'] = multiprocessing.Process(
        target=recolector.correr, args=(snapshot,), daemon=True,
    )
    procesos['recolector'].start()
    time.sleep(0.3)

    for vista, funcion in ANALIZADORES.items():
        p = multiprocessing.Process(
            target=funcion, args=(snapshot, intervalos[vista]), daemon=True,
        )
        p.start()
        procesos[vista] = p

    procesos['display'] = multiprocessing.Process(
        target=display.correr, args=(snapshot, intervalos, config), daemon=True,
    )
    procesos['display'].start()

    manejador = ManejadorSenales()
    print(f'[monitor] {len(procesos)} procesos corriendo '
          f'(recolector + 7 analizadores + display) '
          f'(pid monitor={multiprocessing.current_process().pid})')

    corriendo = True
    while corriendo:
        numero = manejador.esperar_senal(timeout=1)
        if numero is None:
            continue

        print(f'[monitor] recibi {signal.Signals(numero).name}')

        if numero in (signal.SIGINT, signal.SIGTERM):
            corriendo = False
        elif numero == signal.SIGHUP:
            config = cargar_config()
            for vista, valor in config['intervalos'].items():
                intervalos[vista].value = valor
            print(f"[monitor] config recargada: {config['intervalos']}")
        elif numero == signal.SIGUSR1:
            dump_snapshot(snapshot)
        elif numero == signal.SIGUSR2:
            with verbose.get_lock():
                verbose.value = not verbose.value
            print(f'[monitor] modo verbose: {bool(verbose.value)}')

    print('[monitor] shutdown: terminando analizadores...')
    for p in procesos.values():
        p.terminate()
    for p in procesos.values():
        p.join(timeout=2)
    print('[monitor] shutdown limpio completo')


if __name__ == '__main__':
    main()
