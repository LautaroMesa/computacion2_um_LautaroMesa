import argparse
import sys
import re

def crear_parser():
    parser = argparse.ArgumentParser(description="Busca texto en archivos (mini-grep).")
 
    parser.add_argument("patron", help="Texto a buscar")
    parser.add_argument("archivos", nargs="*",  # "*" = cero o más archivos
                        help="Archivos donde buscar (si no se dan, lee stdin)")
    parser.add_argument("-i", "--ignore-case", action="store_true",
                        help="Ignorar mayúsculas/minúsculas")
    parser.add_argument("-n", "--line-number", action="store_true",
                        help="Mostrar número de línea")
    parser.add_argument("-c", "--count", action="store_true",
                        help="Mostrar solo cantidad de coincidencias")
    parser.add_argument("-v", "--invert", action="store_true",
                        help="Mostrar líneas que NO coinciden")
 
    return parser

def buscar_en_lineas(lineas, patron, ignore_case, invert):
    """Devuelve lista de (numero_linea, texto) que coinciden."""
    flags = re.IGNORECASE if ignore_case else 0
    resultados = []
 
    for i, linea in enumerate(lineas, start=1):
        linea = linea.rstrip("\n")
        coincide = bool(re.search(patron, linea, flags))
 
        # Con -v invertimos: queremos las que NO coinciden
        if invert:
            coincide = not coincide
 
        if coincide:
            resultados.append((i, linea))
 
    return resultados

def procesar_archivo(nombre, lineas, args, mostrar_nombre):
    """Procesa las líneas de un archivo y muestra los resultados."""
    resultados = buscar_en_lineas(lineas, args.patron, args.ignore_case, args.invert)
 
    if args.count:
        # Modo --count: solo mostrar cuántas coincidencias hubo
        if mostrar_nombre:
            print(f"{nombre}: {len(resultados)} coincidencias")
        else:
            print(f"{len(resultados)} coincidencias")
        return len(resultados)
 
    for num_linea, texto in resultados:
        partes = []
        if mostrar_nombre:
            partes.append(nombre)
        if args.line_number or mostrar_nombre:
            partes.append(str(num_linea))
        # Unimos con ":" solo las partes que existen
        prefijo = ":".join(partes)
        if prefijo:
            print(f"{prefijo}: {texto}")
        else:
            print(texto)
 
    return len(resultados)

def main():
    parser = crear_parser()
    args = parser.parse_args()
 
    # ¿Hay múltiples archivos? Si es así, mostramos el nombre en cada línea
    mostrar_nombre = len(args.archivos) > 1
 
    if not args.archivos:
        # Sin archivos: leer de stdin (para usar con pipes)
        lineas = sys.stdin.readlines()
        procesar_archivo("stdin", lineas, args, mostrar_nombre=False)
    else:
        total = 0
        for nombre_archivo in args.archivos:
            try:
                with open(nombre_archivo, "r") as f:
                    lineas = f.readlines()
                total += procesar_archivo(nombre_archivo, lineas, args, mostrar_nombre)
            except FileNotFoundError:
                print(f"Error: No se encuentra '{nombre_archivo}'", file=sys.stderr)
 
        # Si usamos --count con múltiples archivos, mostrar el total
        if args.count and mostrar_nombre:
            print(f"Total: {total} coincidencias")
 
if __name__ == "__main__":
    main()