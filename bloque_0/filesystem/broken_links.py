import os
import sys
import argparse


def buscar_links_rotos(directorio):
    """Recorre recursivamente y devuelve lista de (ruta, destino) de symlinks rotos."""
    rotos = []

    for raiz, dirs, archivos in os.walk(directorio, followlinks=False):
        # Revisar tanto archivos como subdirectorios (los symlinks a dirs aparecen en dirs)
        for nombre in archivos + dirs:
            ruta = os.path.join(raiz, nombre)
            try:
                if os.path.islink(ruta) and not os.path.exists(ruta):
                    destino = os.readlink(ruta)
                    rotos.append((ruta, destino))
            except (PermissionError, OSError):
                pass

        # Evitar que os.walk siga symlinks rotos a directorios
        dirs[:] = [
            d for d in dirs
            if not os.path.islink(os.path.join(raiz, d))
        ]

    return rotos


def borrar_con_confirmacion(rotos):
    """Pregunta uno a uno si borrar cada enlace roto."""
    borrados = 0
    for ruta, destino in rotos:
        print(f"\n  {ruta} -> {destino}")
        respuesta = input("  ¿Borrar este enlace? [s/N]: ").strip().lower()
        if respuesta in ("s", "si", "sí", "y", "yes"):
            try:
                os.unlink(ruta)
                print(f"  ✓ Borrado.")
                borrados += 1
            except PermissionError:
                print(f"  ✗ Sin permiso para borrar.")
            except OSError as e:
                print(f"  ✗ Error: {e}")
        else:
            print(f"  — Omitido.")
    return borrados


def main():
    parser = argparse.ArgumentParser(
        description="Buscador de enlaces simbólicos rotos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos:
  python broken_links.py /home/user
  python broken_links.py /home/user --delete
  python broken_links.py /etc --quiet""",
    )

    parser.add_argument("directorio", help="Directorio donde buscar")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Ofrecer borrar los enlaces rotos (con confirmación)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Solo mostrar el conteo de enlaces rotos",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.directorio):
        print(f"Error: '{args.directorio}' no es un directorio válido.")
        sys.exit(1)

    if not args.quiet:
        print(f"Buscando enlaces simbólicos rotos en {args.directorio}...\n")

    rotos = buscar_links_rotos(args.directorio)

    # Modo silencioso: solo el número
    if args.quiet:
        print(len(rotos))
        return

    if not rotos:
        print("No se encontraron enlaces rotos. ✓")
        return

    print("Enlaces rotos encontrados:")
    for ruta, destino in rotos:
        print(f"  {ruta} -> {destino} (no existe)")

    print(f"\nTotal: {len(rotos)} enlace{'s' if len(rotos) != 1 else ''} roto{'s' if len(rotos) != 1 else ''}")

    if args.delete:
        print("\n--- Modo borrado ---")
        borrados = borrar_con_confirmacion(rotos)
        print(f"\nResumen: {borrados} borrado{'s' if borrados != 1 else ''} de {len(rotos)}.")


if __name__ == "__main__":
    main()