import os


def main():
    pid = os.getpid()
    ppid = os.getppid()

    print(f"PID: {pid}")
    print(f"PPID: {ppid}")
    print(f"Directorio actual: {os.getcwd()}")

    print("\nFile descriptors abiertos (/proc/<pid>/fd/):")
    directorio_fd = f'/proc/{pid}/fd'
    for entry in sorted(os.listdir(directorio_fd), key=int):
        try:
            destino = os.readlink(f'{directorio_fd}/{entry}')
        except OSError:
            destino = '?'
        print(f'  {entry} -> {destino}')

    print("\nPrimeras 20 líneas de /proc/<pid>/maps:")
    with open(f'/proc/{pid}/maps', 'r') as f:
        for i, linea in enumerate(f):
            if i >= 20:
                break
            print(f'  {linea.rstrip()}')


if __name__ == '__main__':
    main()
