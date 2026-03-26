import os
import stat
import pwd
import grp
import sys
from datetime import datetime


def formatear_tamanio   (bytes_size):
    """Convierte bytes a formato legible."""
    if bytes_size < 1024:
        return f"{bytes_size} bytes"
    elif bytes_size < 1024 ** 2:
        return f"{bytes_size} bytes ({bytes_size / 1024:.2f} KB)"
    elif bytes_size < 1024 ** 3:
        return f"{bytes_size} bytes ({bytes_size / 1024 ** 2:.2f} MB)"
    else:
        return f"{bytes_size} bytes ({bytes_size / 1024 ** 3:.2f} GB)"


def formatear_permisos(modo):
    """Devuelve permisos en formato rwxr-xr-x y octal."""
    permisos = stat.filemode(modo)[1:]  # saca el primer caracter (tipo)
    octal = oct(stat.S_IMODE(modo))[2:]
    return permisos, octal


def obtener_tipo(modo, ruta):
    """Determina el tipo de archivo."""
    if stat.S_ISREG(modo):
        return "archivo regular"
    elif stat.S_ISDIR(modo):
        return "directorio"
    elif stat.S_ISLNK(modo):
        destino = os.readlink(ruta)
        return f"enlace simbólico -> {destino}"
    elif stat.S_ISCHR(modo):
        return "dispositivo de caracteres"
    elif stat.S_ISBLK(modo):
        return "dispositivo de bloques"
    elif stat.S_ISFIFO(modo):
        return "tubería (FIFO)"
    elif stat.S_ISSOCK(modo):
        return "socket"
    else:
        return "desconocido"


def obtener_propietario(uid):
    """Obtiene el nombre de usuario a partir del uid."""
    try:
        nombre = pwd.getpwuid(uid).pw_name
    except KeyError:
        nombre = "desconocido"
    return nombre


def obtener_grupo(gid):
    """Obtiene el nombre del grupo a partir del gid."""
    try:
        nombre = grp.getgrgid(gid).gr_name
    except KeyError:
        nombre = "desconocido"
    return nombre


def formatear_fecha(timestamp):
    """Convierte timestamp a fecha legible."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def contar_contenido(ruta):
    """Cuenta los elementos dentro de un directorio."""
    try:
        return len(os.listdir(ruta))
    except PermissionError:
        return None


def inspeccionar(ruta):
    """Muestra información detallada sobre un archivo o directorio."""
    if not os.path.lexists(ruta):
        print(f"Error: '{ruta}' no existe.")
        sys.exit(1)

    # Usamos lstat para no seguir el symlink
    info = os.lstat(ruta)
    modo = info.st_mode

    tipo = obtener_tipo(modo, ruta)
    permisos, octal = formatear_permisos(modo)
    propietario = obtener_propietario(info.st_uid)
    grupo = obtener_grupo(info.st_gid)

    print(f"Archivo: {ruta}")
    print(f"Tipo: {tipo}")
    print(f"Tamaño: {formatear_tamanio(info.st_size)}")
    print(f"Permisos: {permisos} ({octal})")
    print(f"Propietario: {propietario} (uid: {info.st_uid})")
    print(f"Grupo: {grupo} (gid: {info.st_gid})")
    print(f"Inodo: {info.st_ino}")
    print(f"Enlaces duros: {info.st_nlink}")

    # Fechas
    # st_birthtime existe en macOS/BSD; en Linux usamos st_ctime como aproximación
    if hasattr(info, "st_birthtime"):
        print(f"Creación:            {formatear_fecha(info.st_birthtime)}")
    else:
        print(f"Creación (ctime):    {formatear_fecha(info.st_ctime)}")

    print(f"Última modificación: {formatear_fecha(info.st_mtime)}")
    print(f"Último acceso:       {formatear_fecha(info.st_atime)}")

    # Info extra para directorios
    if stat.S_ISDIR(modo):
        cantidad = contar_contenido(ruta)
        if cantidad is not None:
            print(f"Contenido: {cantidad} elemento{'s' if cantidad != 1 else ''}")
        else:
            print("Contenido: (sin permiso para leer)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Uso: python {sys.argv[0]} <ruta>")
        sys.exit(1)

    inspeccionar(sys.argv[1])