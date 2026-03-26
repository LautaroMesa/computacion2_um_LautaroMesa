from itertools import islice


def chunked(iterable, size):
    """
    Generador que divide cualquier iterable en chunks de tamaño `size`.
    El último chunk puede tener menos elementos.
    Es lazy: no carga todo en memoria.
    """
    if size < 1:
        raise ValueError(f"El tamaño del chunk debe ser >= 1, se recibió {size}")

    it = iter(iterable)  # unifica cualquier iterable en un iterador
    while True:
        chunk = list(islice(it, size))  # toma hasta `size` elementos
        if not chunk:
            return
        yield chunk
# Demo

if __name__ == "__main__":
    print("=== range(10) en chunks de 3 ===")
    print(list(chunked(range(10), 3)))

    print("\n=== string en chunks de 3 ===")
    print(list(chunked("abcdefgh", 3)))

    print("\n=== lista vacía ===")
    print(list(chunked([], 5)))

    print("\n=== chunk más grande que el iterable ===")
    print(list(chunked([1, 2], 10)))

    print("\n=== generador infinito (primeros 3 chunks de 4) ===")
    def naturales():
        n = 0
        while True:
            yield n
            n += 1

    for i, chunk in enumerate(chunked(naturales(), 4)):
        print(f"  chunk {i}: {chunk}")
        if i == 2:
            break

    print("\n=== lazy: procesar líneas de archivo simulado ===")
    import io
    archivo_simulado = io.StringIO("\n".join(f"línea {i}" for i in range(1, 11)))
    for batch in chunked(archivo_simulado, 3):
        # strip() para sacar el \n de cada línea
        print(f"  batch: {[l.strip() for l in batch]}")