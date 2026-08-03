import os
import subprocess


def correr(comando):
    print(f'$ {comando}')
    resultado = subprocess.run(comando, shell=True, capture_output=True, text=True)
    salida = resultado.stdout or resultado.stderr
    print(salida)
    return salida


def main():
    pid = os.getpid()

    print('=== pstree -p (este proceso) ===')
    correr(f'pstree -p {pid}')

    print('=== ps -ef --forest ===')
    correr('ps -ef --forest')

    print('=== ps -o pid,ppid,comm de este proceso y sus hijos directos ===')
    hijos = subprocess.run(
        f'pgrep -P {pid}', shell=True, capture_output=True, text=True,
    ).stdout.split()
    correr(f'ps -o pid,ppid,comm -p {pid} {" ".join(hijos)}')

    print('=== Análisis ===')
    print('PID 1 es "init" (o el gestor de init del sistema: systemd en la mayoría de'
          ' distros, o el propio proceso que arranca el contenedor cuando corremos'
          ' dentro de Docker) — es el primer proceso que crea el kernel al bootear,'
          ' y todo proceso huérfano termina siendo adoptado por él.')

    print('\nLinaje hacia arriba de ESTE proceso, subiendo por PPID hasta llegar a PID 1:')
    actual = pid
    while actual != 0:
        try:
            with open(f'/proc/{actual}/status', 'r') as f:
                status = f.read()
            nombre = next(l for l in status.splitlines() if l.startswith('Name:')).split()[1]
            ppid_linea = next(l for l in status.splitlines() if l.startswith('PPid:'))
            ppid_actual = int(ppid_linea.split()[1])
        except FileNotFoundError:
            break
        print(f'  PID {actual} ({nombre}) <- padre PID {ppid_actual}')
        if actual == 1:
            break
        actual = ppid_actual


if __name__ == '__main__':
    main()
