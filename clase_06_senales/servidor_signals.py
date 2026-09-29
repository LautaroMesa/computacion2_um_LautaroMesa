#!/usr/bin/env python3
"""Servidor que responde a señales.

Uso:
    python3 servidor_signals.py

Señales:
    kill -HUP <pid>   -> Recargar config (relee config.json)
    kill -USR1 <pid>  -> Mostrar stats
    kill -USR2 <pid>  -> Rotar logs (renombra server.log y abre uno nuevo)
    kill <pid>        -> Shutdown limpio (tambien Ctrl+C)
"""
import json
import os
import signal
import time

ARCHIVO_CONFIG = 'config.json'
ARCHIVO_LOG = 'server.log'
CONFIG_DEFAULT = {"max_conexiones": 100, "timeout": 30}


class Servidor:
    def __init__(self):
        self.ejecutando = True
        self.rotar_pendiente = False
        self.config = self._leer_config()
        self.stats = {"requests": 0, "errores": 0, "inicio": time.time(),
                      "recargas": 0, "rotaciones": 0}
        self.log = open(ARCHIVO_LOG, 'a')

        self._registrar_manejadores()

    def _registrar_manejadores(self):
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGHUP, self._reload_config)
        signal.signal(signal.SIGUSR1, self._mostrar_stats)
        signal.signal(signal.SIGUSR2, self._rotar_logs)

    def _leer_config(self):
        """Lee config.json si existe; si no (o esta roto), usa los defaults.
        Un error en el archivo no tiene que tirar abajo al servidor: en ese
        caso se queda con la config que ya tenia."""
        try:
            with open(ARCHIVO_CONFIG) as f:
                return {**CONFIG_DEFAULT, **json.load(f)}
        except FileNotFoundError:
            return dict(CONFIG_DEFAULT)
        except json.JSONDecodeError as e:
            print(f"[config] {ARCHIVO_CONFIG} invalido ({e}), mantengo la actual")
            return getattr(self, 'config', dict(CONFIG_DEFAULT))

    # --- manejadores ---
    # Los handlers solo tocan estado y hacen prints cortos. El trabajo pesado
    # (el cleanup) queda en el loop principal: el handler solo baja la bandera.

    def _shutdown(self, sig, frame):
        nombre = signal.Signals(sig).name
        print(f"\n[{nombre}] Iniciando shutdown...")
        self.ejecutando = False

    def _reload_config(self, sig, frame):
        print("\n[SIGHUP] Recargando configuracion...")
        self.config = self._leer_config()
        self.config["recargado"] = time.ctime()
        self.stats["recargas"] += 1
        print(f"[SIGHUP] Nueva config: {self.config}")

    def _mostrar_stats(self, sig, frame):
        uptime = time.time() - self.stats["inicio"]
        print("\n[SIGUSR1] === Estadisticas ===")
        print(f"  Uptime: {uptime:.1f}s")
        print(f"  Requests: {self.stats['requests']}")
        print(f"  Errores: {self.stats['errores']}")
        print(f"  Recargas de config: {self.stats['recargas']}")
        print(f"  Rotaciones de log: {self.stats['rotaciones']}")
        print(f"  Config: {self.config}")

    def _rotar_logs(self, sig, frame):
        # No rotamos aca adentro: el handler puede correr entre que el loop
        # agarro self.log y llamo a .write(), y escribiria en un archivo ya
        # cerrado. Solo pedimos la rotacion y la hace el loop principal.
        print("\n[SIGUSR2] Rotacion pedida")
        self.rotar_pendiente = True

    def rotar_logs(self):
        # Lo mismo que hace logrotate con nginx/apache: renombrar el archivo
        # actual y reabrir uno nuevo con el nombre original.
        self.rotar_pendiente = False
        self.log.close()
        destino = f"{ARCHIVO_LOG}.{int(time.time())}"
        os.rename(ARCHIVO_LOG, destino)
        self.log = open(ARCHIVO_LOG, 'a')
        self.stats["rotaciones"] += 1
        print(f"[SIGUSR2] Logs rotados a {destino}")

    # --- trabajo ---

    def procesar_request(self):
        """Simula procesamiento de una request."""
        self.stats["requests"] += 1
        time.sleep(0.1)
        if self.stats["requests"] % 10 == 0:
            self.stats["errores"] += 1
            self.log.write(f"{time.ctime()} ERROR en request {self.stats['requests']}\n")
        else:
            self.log.write(f"{time.ctime()} request {self.stats['requests']} ok\n")
        self.log.flush()

    def run(self):
        pid = os.getpid()
        print(f"Servidor iniciado (PID {pid})")
        print("Comandos disponibles:")
        print(f"  kill -HUP {pid}   -> Recargar config")
        print(f"  kill -USR1 {pid}  -> Ver stats")
        print(f"  kill -USR2 {pid}  -> Rotar logs")
        print(f"  kill {pid}        -> Shutdown")
        print()

        while self.ejecutando:
            if self.rotar_pendiente:
                self.rotar_logs()
            self.procesar_request()

        self.cleanup()

    def cleanup(self):
        print("Realizando cleanup...")
        self.log.write(f"{time.ctime()} shutdown, {self.stats['requests']} requests\n")
        self.log.close()
        print(f"Servidor terminado. Requests procesadas: {self.stats['requests']}")


if __name__ == "__main__":
    Servidor().run()
