import time
from contextlib import contextmanager

# Implementación 1: clase con __enter__ / __exit__

class Timer:
    def __init__(self, nombre=None):
        self.nombre = nombre
        self._inicio = None
        self.elapsed = 0.0

    def __enter__(self):
        self._inicio = time.perf_counter()
        return self  # permite usar "as t"

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.perf_counter() - self._inicio
        if self.nombre:
            print(f"[Timer] {self.nombre}: {self.elapsed:.3f}s")
        return False  # no suprime excepciones

    @property
    def elapsed(self):
        """Permite leer el tiempo transcurrido DURANTE el bloque."""
        if self._inicio is None:
            return self._elapsed
        return time.perf_counter() - self._inicio

    @elapsed.setter
    def elapsed(self, valor):
        self._elapsed = valor

# Implementación 2: @contextmanager de contextlib

@contextmanager
def timer(nombre=None):
    inicio = time.perf_counter()

    # Objeto simple para exponer .elapsed
    class _T:
        @property
        def elapsed(self):
            return time.perf_counter() - inicio

    t = _T()
    try:
        yield t
    finally:
        t_final = time.perf_counter() - inicio
        # Fijar elapsed como valor fijo al salir
        t.__class__ = type("_T", (), {"elapsed": t_final})
        if nombre:
            print(f"[Timer] {nombre}: {t_final:.3f}s")

# Pruebas de uso

if __name__ == "__main__":
    print("=== Clase Timer ===\n")

    # Con nombre → imprime automáticamente al salir
    with Timer("Procesamiento de datos"):
        datos = [x**2 for x in range(1000000)]

    print()

    # Sin nombre → acceso manual a t.elapsed
    with Timer() as t:
        time.sleep(0.5)
    print(f"El bloque tardó {t.elapsed:.3f} segundos")

    print()

    # Acceso durante el bloque
    with Timer() as t:
        time.sleep(0.1)
        print(f"  Después del paso 1: {t.elapsed:.3f}s")
        time.sleep(0.2)
        print(f"  Después del paso 2: {t.elapsed:.3f}s")

    print()
    print("─" * 40)
    print("\n=== @contextmanager timer ===\n")

    with timer("Procesamiento de datos"):
        datos = [x**2 for x in range(1000000)]

    print()

    with timer() as t:
        time.sleep(0.5)
    print(f"El bloque tardó {t.elapsed:.3f} segundos")

    print()

    with timer() as t:
        time.sleep(0.1)
        print(f"  Después del paso 1: {t.elapsed:.3f}s")
        time.sleep(0.2)
        print(f"  Después del paso 2: {t.elapsed:.3f}s")