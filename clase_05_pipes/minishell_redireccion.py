import os
import shlex
import sys


def parsear_linea(linea):
    """"ls -la" -> ("ls", ["-la"], None, None)
    "ls > out.txt" -> ("ls", [], "out.txt", None)
    "cat < in.txt" -> ("cat", [], None, "in.txt")

    Usa shlex en vez de un split() ingenuo para que algo como
    echo "hola mundo" > archivo.txt trate "hola mundo" como UN solo
    argumento (respetando las comillas), en vez de partirlo en dos.
    """
    tokens = shlex.split(linea)
    archivo_salida = None
    archivo_entrada = None
    resto = []

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == '>':
            i += 1
            archivo_salida = tokens[i]
        elif tok == '<':
            i += 1
            archivo_entrada = tokens[i]
        else:
            resto.append(tok)
        i += 1

    if not resto:
        return None, [], archivo_salida, archivo_entrada
    return resto[0], resto[1:], archivo_salida, archivo_entrada


def ejecutar(comando, args, archivo_salida, archivo_entrada):
    pid = os.fork()

    if pid == 0:
        # La redireccion se resuelve ANTES del execvp: abrimos el archivo y
        # con dup2 lo "pisamos" sobre el fd 0 (stdin) o 1 (stdout). Como
        # execvp reemplaza el codigo del proceso pero NO su tabla de file
        # descriptors, el comando que arranca despues hereda esos fds ya
        # redirigidos sin enterarse de nada.
        if archivo_entrada:
            fd_in = os.open(archivo_entrada, os.O_RDONLY)
            os.dup2(fd_in, 0)
            os.close(fd_in)

        if archivo_salida:
            fd_out = os.open(
                archivo_salida, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644,
            )
            os.dup2(fd_out, 1)
            os.close(fd_out)

        try:
            os.execvp(comando, [comando] + args)
        except OSError as e:
            print(f'{comando}: {e}', file=sys.stderr)
            os._exit(1)
    else:
        _, status = os.waitpid(pid, 0)
        if os.WIFEXITED(status):
            codigo = os.WEXITSTATUS(status)
            if codigo != 0:
                print(f'[Salió con código {codigo}]')


def main():
    while True:
        try:
            linea = input('minish$ ')
        except EOFError:
            break

        linea = linea.strip()
        if not linea:
            continue

        if linea == 'exit':
            break

        try:
            comando, args, archivo_salida, archivo_entrada = parsear_linea(linea)
        except ValueError as e:
            print(f'minish: error de sintaxis: {e}', file=sys.stderr)
            continue

        if comando is None:
            continue

        if comando == 'cd':
            destino = args[0] if args else os.environ.get('HOME', '/')
            try:
                os.chdir(destino)
            except OSError as e:
                print(f'cd: {e}')
            continue

        ejecutar(comando, args, archivo_salida, archivo_entrada)


if __name__ == '__main__':
    main()
