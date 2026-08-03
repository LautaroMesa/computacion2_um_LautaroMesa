import subprocess
import time


def clasificar(linea):
    partes = linea.split(maxsplit=5)
    permisos = partes[1]
    etiqueta = partes[5].strip() if len(partes) > 5 else ''

    if '[heap]' in etiqueta:
        return 'HEAP'
    if '[stack]' in etiqueta:
        return 'STACK'
    if 'x' in permisos and etiqueta.endswith('python3.11'):
        return 'TEXT (ejecutable)'
    if etiqueta.startswith('/'):
        return 'librería cargada'
    return None


def main():
    # Lanzamos un proceso de fondo real, igual que "python3 -c '...' &" en bash
    proceso = subprocess.Popen(['python3', '-c', 'import time; time.sleep(60)'])
    time.sleep(0.3)  # darle tiempo a que termine de mapear su memoria

    print(f'Proceso de fondo lanzado, PID={proceso.pid}\n')

    with open(f'/proc/{proceso.pid}/maps', 'r') as f:
        for linea in f:
            tipo = clasificar(linea)
            if tipo:
                print(f'[{tipo:20}] {linea.rstrip()}')

    proceso.terminate()
    proceso.wait()


if __name__ == '__main__':
    main()
