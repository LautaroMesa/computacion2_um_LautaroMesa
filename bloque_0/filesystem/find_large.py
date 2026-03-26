import os
import stat
import sys
import argparse
import re


def parsear_tamanio(texto):
    """Convierte '1M', '500K', '2G' a bytes. Sin sufijo = bytes directos."""
    texto = texto.strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMG]?)", texto, re.IGNORECASE)
    if not match:
        raise argparse.ArgumentTypeError(
            f"Tamaño inválido: '{texto}'. Usá formatos como 100K, 1M, 2G o bytes directos."
        )
    valor, unidad = float(match.group(1)), match.group(2).upper()
    multiplicadores = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}
    return int(valor * multiplicadores[unidad])


def formatear_tamanio(bytes_size):
    """Convierte bytes al formato más legible (KB, MB, GB)."""
    if bytes_size >= 1024**3:
        return f"{bytes_size / 1024**3:.1f} GB"
    elif bytes_size >= 1024**2:
        return f"{bytes_size / 1024**2:.1f} MB"
    elif bytes_size >= 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size} bytes"


def es_tipo(modo, tipo):
    """Verifica si el modo coincide con el tipo pedido ('f' o 'd')."""
    if tipo == "f":
        return stat.S_ISREG(modo)
    elif tipo == "d":
        return stat.S_ISDIR(modo)
    return True  # sin filtro


def buscar(directorio, min_size, tipo, top):
    """Recorre recursivamente y recolecta entradas que cumplan los filtros."""
    resultados = []
    errores = 0

    for raiz, dirs, archivos in os.walk(directorio, followlinks=False):
        # Incluir archivos regulares
        entradas = archivos if tipo == "f" else (archivos + dirs) if tipo is None else dirs

        for nombre in entradas:
            ruta = os.path.join(raiz, nombre)
            try:
                info = os.lstat(ruta)
                modo = info.st_mode

                if not es_tipo(modo, tipo):
                    continue

                if info.st_size >= min_size:
                    resultados.append((ruta, info.st_size))

            except (PermissionError, FileNotFoundError, OSError):
                errores += 1

        # También evaluar el propio directorio raíz si el tipo es 'd'
        if tipo == "d":
            try:
                info = os.lstat(raiz)
                if info.st_size >= min_size:
                    # evitar duplicados (os.walk ya visita subdirs)
                    if raiz == directorio:
                        resultados.append((raiz, info.st_size))
            except OSError:
                pass

    # Ordenar de mayor a menor
    resultados.sort(key=lambda x: x[1], reverse=True)

    if top:
        resultados = resultados[:top]

    return resultados, errores


def main():
    parser = argparse.ArgumentParser(
        description="Buscador de archivos grandes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos:
  python find_large.py /var/log --min-size 1M
  python find_large.py . --min-size 100K --type f
  python find_large.py /home --min-size 50M --top 10""",
    )

    parser.add_argument("directorio", help="Directorio donde buscar")
    parser.add_argument(
        "--min-size",
        default="1M",
        type=parsear_tamanio,
        metavar="TAMAÑO",
        help="Tamaño mínimo (ej: 100K, 1M, 2G). Por defecto: 1M",
    )
    parser.add_argument(
        "--type",
        choices=["f", "d"],
        dest="tipo",
        default=None,
        metavar="TIPO",
        help="Tipo de entrada: f=archivo, d=directorio",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="Mostrar solo los N más grandes",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.directorio):
        print(f"Error: '{args.directorio}' no es un directorio válido.")
        sys.exit(1)

    resultados, errores = buscar(args.directorio, args.min_size, args.tipo, args.top)

    if not resultados:
        print(f"No se encontraron archivos mayores a {formatear_tamanio(args.min_size)}.")
        return

    if args.top:
        print(f"Los {args.top} archivos más grandes:")
        for i, (ruta, tamanio) in enumerate(resultados, 1):
            print(f"  {i:2}. {ruta} ({formatear_tamanio(tamanio)})")
    else:
        for ruta, tamanio in resultados:
            print(f"{ruta} ({formatear_tamanio(tamanio)})")

    total_bytes = sum(t for _, t in resultados)
    cantidad = len(resultados)
    print(f"\nTotal: {cantidad} archivo{'s' if cantidad != 1 else ''}, {formatear_tamanio(total_bytes)}")

    if errores:
        print(f"(Se omitieron {errores} entradas por falta de permisos)")


if __name__ == "__main__":
    main()