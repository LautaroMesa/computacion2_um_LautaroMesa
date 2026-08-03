import sys

MENSAJE_DEFAULT = 'Muuu, Docker!'


def cowsay(mensaje):
    ancho = len(mensaje) + 2
    print(' ' + '_' * ancho)
    print(f'< {mensaje} >')
    print(' ' + '-' * ancho)
    print(r'''        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||''')


if __name__ == '__main__':
    mensaje = ' '.join(sys.argv[1:]) or MENSAJE_DEFAULT
    cowsay(mensaje)
