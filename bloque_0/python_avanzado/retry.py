import time
import random
import functools


def retry(max_attempts=3, delay=1, exceptions=Exception):
    """
    Decorador que reintenta una función si lanza una excepción.

    Parámetros:
        max_attempts: número máximo de intentos (default: 3)
        delay:        segundos a esperar entre intentos (default: 1)
        exceptions:   excepción o tupla de excepciones a capturar (default: Exception)
    """
    # Normalizar: permitir pasar una sola excepción o una tupla
    exc_tupla = exceptions if isinstance(exceptions, tuple) else (exceptions,)

    def decorador(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ultimo_error = None

            for intento in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except exc_tupla as e:
                    ultimo_error = e
                    es_ultimo = intento == max_attempts

                    if es_ultimo:
                        print(f"Intento {intento}/{max_attempts} falló: {e}.")
                    else:
                        print(f"Intento {intento}/{max_attempts} falló: {e}. Esperando {delay}s...")
                        time.sleep(delay)

            raise ultimo_error

        return wrapper
    return decorador

# Prueba de uso 

if __name__ == "__main__":
    print("=== Caso 1: falla todos los intentos ===\n")

    @retry(max_attempts=3, delay=0.5)
    def conectar_servidor():
        if random.random() < 0.7:
            raise ConnectionError("Servidor no disponible")
        return "Conectado exitosamente"

    random.seed(42)  # semilla fija para resultado reproducible
    try:
        resultado = conectar_servidor()
        print(f"✓ {resultado}")
    except ConnectionError as e:
        print(f"✗ Falló después de 3 intentos: {e}")

    print()
    print("=== Caso 2: éxito en el segundo intento ===\n")

    intentos_globales = 0

    @retry(max_attempts=3, delay=0.2)
    def tarea_inestable():
        global intentos_globales
        intentos_globales += 1
        if intentos_globales < 2:
            raise TimeoutError("Timeout de conexión")
        return "Operación completada"

    try:
        resultado = tarea_inestable()
        print(f"✓ {resultado}")
    except TimeoutError as e:
        print(f"✗ {e}")

    print()
    print("=== Caso 3: exceptions filtra el tipo ===\n")

    @retry(max_attempts=3, delay=0.1, exceptions=(ValueError, TypeError))
    def validar_dato(x):
        if x < 0:
            raise ValueError(f"Valor negativo: {x}")
        if not isinstance(x, int):
            raise TypeError(f"Tipo incorrecto: {type(x)}")
        return x * 2

    # ValueError es capturada → reintenta
    try:
        validar_dato(-1)
    except ValueError as e:
        print(f"✗ ValueError capturada tras 3 intentos: {e}")

    print()

    # RuntimeError NO está en la tupla → se propaga sin reintentar
    @retry(max_attempts=3, delay=0.1, exceptions=(ValueError,))
    def puede_fallar():
        raise RuntimeError("Este error no se reintenta")

    try:
        puede_fallar()
    except RuntimeError as e:
        print(f"✗ RuntimeError propagada sin reintentos: {e}")