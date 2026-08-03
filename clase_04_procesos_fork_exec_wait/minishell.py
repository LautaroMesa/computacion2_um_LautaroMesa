import os
import sys


def main():
    while True:
        try:
            linea = input('$ ')
        except EOFError:
            break

        linea = linea.strip()
        if not linea:
            continue

        partes = linea.split()
        comando, args = partes[0], partes[1:]

        if comando == 'exit':
            break

        if comando == 'cd':
            # cd tiene que afectar al PROPIO proceso del shell, asi que NO
            # se puede resolver con fork+exec (un hijo cambiaria SU cwd, no
            # el del shell) - es un builtin.
            destino = args[0] if args else os.environ.get('HOME', '/')
            try:
                os.chdir(destino)
            except OSError as e:
                print(f'cd: {e}')
            continue

        pid = os.fork()

        if pid == 0:
            # Proceso hijo: se reemplaza a si mismo por el comando pedido.
            try:
                os.execvp(comando, [comando] + args)
            except OSError as e:
                # stderr, no stdout: es semanticamente lo correcto para un
                # error, y ademas evita perder el mensaje. os._exit() no
                # flushea los buffers de stdio (a diferencia de sys.exit()),
                # y stdout viene buffereado por bloques cuando no es una
                # terminal (ej. corriendo con stdin/stdout redirigidos) -
                # print() ahi se hubiera perdido. stderr en Python es
                # unbuffered/line-buffered siempre, sin ese problema.
                print(f'{comando}: {e}', file=sys.stderr)
                os._exit(1)
        else:
            # Proceso padre (el shell): espera a que el hijo termine.
            _, status = os.waitpid(pid, 0)
            if os.WIFEXITED(status):
                codigo = os.WEXITSTATUS(status)
                if codigo != 0:
                    print(f'[Salió con código {codigo}]')


if __name__ == '__main__':
    main()
