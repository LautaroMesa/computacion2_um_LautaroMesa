import sys
import urllib.request

# El nombre "servidor" no es un hostname real de internet: Docker resuelve
# los nombres de los contenedores conectados a la MISMA red custom via su
# propio DNS interno. Por eso esto funciona sin saber la IP del servidor.
HOST = 'servidor'
PUERTO = 8000


def main():
    url = f'http://{HOST}:{PUERTO}/'
    print(f'Pidiendo {url} ...')
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            print(f'Status: {resp.status}')
            print(resp.read().decode())
    except urllib.error.URLError as e:
        print(f'No se pudo conectar a {HOST}: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
