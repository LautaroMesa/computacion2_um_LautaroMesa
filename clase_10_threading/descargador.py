#!/usr/bin/env python3
"""Descargador paralelo con un pool fijo de threads hecho a mano.

N workers (threading.Thread) toman URLs de una queue.Queue hasta recibir el
centinela None. Los resultados se guardan en una lista protegida por Lock.
Los errores de red se registran como resultado fallido: un worker nunca se
muere por una URL mala (si se muriera, sus URLs pendientes no se procesarian).

Uso:
    python3 descargador.py                    # lista de URLs de ejemplo
    python3 descargador.py -w 8 URL [URL...]
    python3 descargador.py --secuencial       # misma lista, 1 sola descarga a la vez
"""
import argparse
import queue
import threading
import time
import urllib.error
import urllib.request

URLS_EJEMPLO = [
    "https://www.python.org",
    "https://docs.python.org",
    "https://pypi.org",
    "https://www.google.com",
    "https://www.github.com",
    "https://www.um.edu.ar",
    "https://httpbin.org/delay/2",            # tarda 2 s a proposito
    "https://httpbin.org/status/404",         # error HTTP
    "https://no-existe.invalid",              # error de DNS
    "http://10.255.255.1",                    # no responde: se corta por timeout
]
TIMEOUT = 5
# perf_counter y no time(): time() es el reloj de pared y lo puede ajustar
# NTP en medio de una medicion (en WSL llego a dar una duracion negativa).


def descargar(url):
    """Descarga una URL y devuelve un dict con el resultado (nunca lanza)."""
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            datos = resp.read()
        return {"url": url, "ok": True, "bytes": len(datos),
                "tiempo": time.perf_counter() - inicio}
    except urllib.error.HTTPError as e:
        error = f"HTTP {e.code}"
    except urllib.error.URLError as e:
        error = f"URLError: {e.reason}"
    except (TimeoutError, OSError) as e:
        error = f"{type(e).__name__}: {e}"
    return {"url": url, "ok": False, "error": error,
            "tiempo": time.perf_counter() - inicio}


def worker(in_q, resultados, lock):
    nombre = threading.current_thread().name
    while True:
        url = in_q.get()
        if url is None:
            in_q.task_done()
            break
        r = descargar(url)
        r["worker"] = nombre
        with lock:
            resultados.append(r)
        in_q.task_done()


def con_pool(urls, num_workers):
    in_q = queue.Queue()
    resultados = []
    lock = threading.Lock()

    workers = [threading.Thread(target=worker, args=(in_q, resultados, lock),
                                name=f"W{i}")
               for i in range(num_workers)]
    for w in workers:
        w.start()

    for url in urls:
        in_q.put(url)
    for _ in workers:          # un centinela por worker
        in_q.put(None)

    for w in workers:
        w.join()
    return resultados


def secuencial(urls):
    return [dict(descargar(u), worker="main") for u in urls]


def main():
    parser = argparse.ArgumentParser(description="Descargador paralelo con threads")
    parser.add_argument("urls", nargs="*", default=URLS_EJEMPLO)
    parser.add_argument("-w", "--workers", type=int, default=4)
    parser.add_argument("--secuencial", action="store_true")
    args = parser.parse_args()

    inicio = time.perf_counter()
    if args.secuencial:
        resultados = secuencial(args.urls)
    else:
        resultados = con_pool(args.urls, args.workers)
    tiempo_total = time.perf_counter() - inicio

    for r in sorted(resultados, key=lambda r: r["tiempo"]):
        if r["ok"]:
            detalle = f"{r['bytes']:>9,} bytes"
        else:
            detalle = f"ERROR {r['error']}"
        print(f"[{r['worker']:>4}] {r['tiempo']:5.2f}s  {r['url']:<32} {detalle}")

    ok = [r for r in resultados if r["ok"]]
    modo = "secuencial" if args.secuencial else f"{args.workers} workers"
    print(f"\nModo: {modo}")
    print(f"Descargas exitosas: {len(ok)}/{len(args.urls)}")
    print(f"Bytes totales: {sum(r['bytes'] for r in ok):,}")
    print(f"Suma de tiempos individuales: {sum(r['tiempo'] for r in resultados):.2f}s")
    print(f"Tiempo total: {tiempo_total:.2f}s")


if __name__ == "__main__":
    main()
