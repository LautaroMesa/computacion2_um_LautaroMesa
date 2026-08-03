import subprocess


def main():
    with open('/proc/sys/kernel/pid_max', 'r') as f:
        pid_max = int(f.read().strip())
    print(f'pid_max del sistema: {pid_max}\n')

    print('Lanzando 20 procesos seguidos y mostrando su PID:')
    pids = []
    for _ in range(20):
        resultado = subprocess.run(
            ['sh', '-c', 'echo "PID=$$"'], capture_output=True, text=True,
        )
        pid = int(resultado.stdout.strip().split('=')[1])
        pids.append(pid)
        print(f'  {pid}')

    print(f'\nRango observado: {min(pids)} - {max(pids)}')
    print('Los PIDs suben de a poco (el kernel asigna el siguiente libre), pero no'
          ' son infinitos: al llegar a pid_max, el contador vuelve a buscar desde'
          ' abajo el primer numero libre. Con solo 20 procesos no vamos a ver el'
          ' reciclado en vivo (pid_max suele ser >4 millones), pero el mecanismo'
          ' es ese: reciclar, no crecer para siempre.')


if __name__ == '__main__':
    main()
