import time

import agregador
import procfs


def correr(snapshot, intervalo=1.0):
    """Componente Recolector: lista /proc UNA sola vez por vuelta y publica
    esa lista de PIDs en el snapshot compartido.

    Los 7 analizadores leen de ahi (via pids_actuales()) en vez de llamar
    cada uno a os.listdir('/proc') por su cuenta. El intervalo es mas rapido
    que el de cualquier vista (1s por defecto) para que la lista este
    siempre fresca cuando un analizador la consulta.
    """
    agregador.ignorar_sigint()
    while True:
        agregador.publicar(snapshot, '_pids', procfs.listar_pids())
        time.sleep(intervalo)


def pids_actuales(snapshot):
    return snapshot['_pids']['datos']
