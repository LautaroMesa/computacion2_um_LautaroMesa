#!/usr/bin/env python3
"""Test del ReadWriteLock (el de la consigna, con verificacion agregada).

5 lectores (5 lecturas c/u) y 2 escritores (3 escrituras c/u), arrancados en
orden aleatorio. Ademas de imprimir lo que pasa, un "monitor" registra cuantos
lectores y escritores hay adentro en cada momento y verifica las reglas:
  - nunca un lector y un escritor a la vez
  - nunca dos escritores a la vez
  - en algun momento hubo mas de un lector a la vez (si no, el lock seria
    un Lock comun disfrazado)
"""
import random
import threading
import time

from rwlock import ReadLock, ReadWriteLock, WriteLock

rwlock = ReadWriteLock()
datos = {"valor": 0, "lecturas": 0, "escrituras": 0}

# Monitor de verificacion (con su propio lock, independiente del rwlock)
_mon = threading.Lock()
adentro = {"lectores": 0, "escritores": 0}
maximos = {"lectores": 0, "escritores": 0}
violaciones = []


def entrar(tipo):
    with _mon:
        adentro[tipo] += 1
        maximos[tipo] = max(maximos[tipo], adentro[tipo])
        if adentro["escritores"] > 1:
            violaciones.append(f"dos escritores a la vez: {adentro}")
        if adentro["escritores"] and adentro["lectores"]:
            violaciones.append(f"lector y escritor a la vez: {adentro}")
        return adentro[tipo]


def salir(tipo):
    with _mon:
        adentro[tipo] -= 1


def lector(id):
    for _ in range(5):
        with ReadLock(rwlock):
            n = entrar("lectores")
            valor = datos["valor"]
            # datos["lecturas"] += 1 NO es atomico y hay varios lectores
            # adentro a la vez: ese contador va bajo el lock del monitor
            with _mon:
                datos["lecturas"] += 1
            print(f"[Lector {id}] Leyo valor={valor}  (lectores adentro: {n})")
            time.sleep(random.uniform(0.05, 0.15))
            salir("lectores")
        time.sleep(random.uniform(0.1, 0.2))


def escritor(id):
    for i in range(3):
        with WriteLock(rwlock):
            entrar("escritores")
            datos["valor"] = id * 100 + i
            datos["escrituras"] += 1
            print(f"[Escritor {id}] Escribio valor={datos['valor']}")
            time.sleep(random.uniform(0.1, 0.2))
            salir("escritores")
        time.sleep(random.uniform(0.2, 0.4))


if __name__ == "__main__":
    threads = [threading.Thread(target=lector, args=(i,)) for i in range(5)]
    threads += [threading.Thread(target=escritor, args=(i,)) for i in range(2)]
    random.shuffle(threads)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\nEstadisticas finales:")
    print(f"  Valor final: {datos['valor']}")
    print(f"  Total lecturas: {datos['lecturas']} (esperadas 25)")
    print(f"  Total escrituras: {datos['escrituras']} (esperadas 6)")
    print(f"  Maximo de lectores simultaneos: {maximos['lectores']}")
    print(f"  Maximo de escritores simultaneos: {maximos['escritores']}")
    if violaciones:
        print(f"  VIOLACIONES: {len(violaciones)}")
        for v in violaciones[:5]:
            print(f"    {v}")
    else:
        print("  Violaciones de las reglas: ninguna")
