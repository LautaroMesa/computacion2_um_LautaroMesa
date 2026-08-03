import signal
import time

VISTAS = ['resumen', 'memoria', 'fds', 'threads', 'senales', 'scheduling', 'sistema']


def ignorar_sigint():
    """Los analizadores hijos comparten grupo de procesos con el monitor, asi
    que un Ctrl+C en la terminal les llega a TODOS, no solo al padre. Sin esto,
    cada hijo levantaria un KeyboardInterrupt con su propio traceback feo. El
    unico que decide el shutdown es el proceso principal (via self-pipe en
    senales.py); a los hijos los para con .terminate() (SIGTERM).
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def crear_snapshot_inicial(manager):
    snapshot = manager.dict()
    for vista in VISTAS:
        snapshot[vista] = {'datos': [], 'ts': 0.0}
    # '_pids' no es una vista de la TUI: es el canal por el que el Recolector
    # le pasa la lista de PIDs a los 7 analizadores (ver recolector.py).
    snapshot['_pids'] = {'datos': [], 'ts': 0.0}
    return snapshot


def publicar(snapshot, vista, datos):
    # snapshot[vista] guarda un dict PLANO (no un Manager.dict anidado), asi que
    # leerlo te da una copia pickleada, no una referencia al original. Por eso hay
    # que reasignar la entrada entera de una: snapshot[vista] = {...} es lo que
    # dispara el envio al proceso servidor del Manager. Si en cambio hicieramos
    # snapshot[vista]['ts'] = time.time(), estariamos mutando una copia local que
    # se descarta enseguida y el servidor nunca se entera.
    snapshot[vista] = {'datos': datos, 'ts': time.time()}
