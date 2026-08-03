import os
import select
import signal

SENALES_MANEJADAS = [
    signal.SIGINT, signal.SIGTERM, signal.SIGHUP,
    signal.SIGUSR1, signal.SIGUSR2,
]


class ManejadorSenales:
    """Implementa el patron self-pipe: los handlers solo escriben 1 byte a un
    pipe interno. El trabajo real se procesa despues, en esperar_senal(),
    que corre en el loop principal (contexto normal, no signal handler).
    """

    def __init__(self):
        self._read_fd, self._write_fd = os.pipe()
        os.set_blocking(self._read_fd, False)
        for sen in SENALES_MANEJADAS:
            signal.signal(sen, self._handler)

    def _handler(self, numero_senal, frame):
        # UNICA operacion permitida aca: write() a un fd es async-signal-safe.
        os.write(self._write_fd, bytes([numero_senal]))

    def esperar_senal(self, timeout):
        listos, _, _ = select.select([self._read_fd], [], [], timeout)
        if not listos:
            return None
        return os.read(self._read_fd, 1)[0]
