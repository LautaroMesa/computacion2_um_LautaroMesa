# Clase 17 — I/O Multiplexing

Ejercicio obligatorio 3: comparar `select`, `poll` y `epoll`.

## Archivos

| Archivo | Qué es |
|---|---|
| `comparar.py` | El benchmark de la cátedra. Le agregué `--activos N` (o `--activos mitad`) para la pregunta 7 sin tener que editar la constante |

## Cómo correr

```bash
docker build -t clase17 .
docker run --rm --ulimit nofile=20000:20000 clase17 python comparar.py
docker run --rm --ulimit nofile=20000:20000 clase17 python comparar.py --activos mitad
docker run --rm clase17 python comparar.py 10 50 100
```

5000 conexiones son 10.000 descriptores (cada `socketpair` crea dos), así que
hace falta subir el límite de fds abiertos (`--ulimit` en Docker o `ulimit -n`
en la terminal).

Máquina: Ubuntu 24.04 en WSL2, Python 3.12, 16 CPUs lógicas.

---

## Parte A: correr el benchmark

**1.** Microsegundos por llamada, 3 sockets con datos (3 corridas; muestro la
primera, las otras dos dieron lo mismo con ±10%):

```
 conexiones     select       poll      epoll
---------------------------------------------
        100      14.5       7.0       1.3
        500      75.8      36.6       1.4
       1000 falla (ValueError)      78.4       1.3
       2000 falla (ValueError)     348.8       1.4
       5000 falla (ValueError)    1500.5       1.4
```

**2. Crecimiento de `poll()`:** de 7,0 µs (100) a 1500 µs (5000). Con **50 veces**
más conexiones tarda **~214 veces** más. Es O(n), y además peor que lineal en los
tamaños grandes: de 1000 a 5000 (5x) el tiempo crece 19x. Supongo que es un efecto de
caché: con miles de fds, el arreglo `pollfd` y las estructuras del kernel que se
recorren ya no entran en la caché del procesador.

**3. `epoll()`:** plano, entre 1,0 y 1,6 µs de 100 a 5000 conexiones. El costo
**no depende** de cuántas conexiones hay registradas. Con 5000 conexiones,
`epoll` es ~1000 veces más rápido que `poll`.

**4. ¿Cuándo falla `select()`?** A partir de **1000** conexiones, con
`ValueError`. Coincide con el 2.3:

```
fd: 1104
select: ValueError filedescriptor out of range in select()
poll OK: [(1104, 16)]
```

Vigilando **un solo** socket, `select` falla si su **número** de fd es ≥ 1024
(`FD_SETSIZE`). Con 1000 conexiones hay 2000 fds abiertos, y los lectores
tienen números mayores que 1023. Con 500 conexiones, los fds llegan a ~1000 y
todavía funciona. El límite es **el valor del fd, no la cantidad**: `select`
usa un bitmap fijo de 1024 bits indexado por número de fd. Por eso aparece en
producción y no en desarrollo: un servidor que lleva días corriendo o que abre
archivos y logs tiene fds altos aunque vigile pocos sockets. `poll` y `epoll`
no tienen ese límite.

## Parte B: entender el porqué

**5. ¿Por qué es realista que solo 3 de 5000 tengan datos?** Porque en un
servidor web la mayoría de las conexiones está **ociosa** casi todo el tiempo:
conexiones keep-alive esperando el próximo pedido, clientes móviles con red
lenta, websockets abiertos que mandan algo cada tanto, navegadores leyendo la
página que ya recibieron. En un instante dado, solo un puñado tiene bytes
listos. El costo del multiplexor tiene que depender de ese puñado, no del total.

**6. O(n) contra O(listos).**
- `poll()` (y `select()`) no guardan estado entre llamadas: en **cada** llamada
  el programa le pasa al kernel la lista **completa** de fds (copiada de
  espacio de usuario al kernel). El kernel recorre **todos** consultando si están
  listos, marca los resultados y copia todo de vuelta. Después, Python recorre la
  lista para encontrar los listos. Todo eso es proporcional a n, aunque haya 3
  activos.
- `epoll` separa el registro de la espera. `epoll_ctl` registra cada fd **una
  vez** en una estructura que vive en el kernel. Cuando llegan datos a un socket,
  el propio kernel (desde el camino de recepción) agrega ese fd a una **lista de
  listos**. `epoll_wait` solo entrega esa lista, sin recorrer los que no tienen
  nada. El trabajo de cada llamada es proporcional a los listos.

**7. Con la mitad activa** (`--activos mitad`):

```
 conexiones     select       poll      epoll
---------------------------------------------
        100      19.4       7.8       8.7
        500      78.3      46.9      41.5
       1000 falla (ValueError)     103.6      90.2
       2000 falla (ValueError)     374.5     229.6
       5000 falla (ValueError)    1628.3     461.2
```

**La ventaja casi desaparece.** Con 100 conexiones y 50 listas, `epoll` ya es
algo más lento que `poll`, y hasta 1000 están parejos. Si la mitad está lista,
"O(listos)" es O(n/2): `epoll` también tiene que armar y devolver una lista
proporcional a n, y `poll` no tiene nada que ahorrarse porque de todos modos
iba a encontrar muchos listos.

El 461 µs de `epoll` en 5000 **está subestimado**. Python limita cada
`epoll.poll()` a `maxevents = 1023` por defecto, así que con 2500 listos solo
devuelve 1023 por llamada (lo verifiqué: `len(ep.poll(0))` da 1023 con 3000
listos, y 3000 con `maxevents=5000`). Para procesar los 2500 harían falta 3
llamadas, lo que lo acerca a `poll`.

## Parte C: el caso donde no importa

**8.** `comparar.py 10 50 100`:

```
 conexiones     select       poll      epoll
---------------------------------------------
         10       2.3       1.3       1.3
         50       7.0       3.8       1.0
        100      13.5       7.3       1.0
```

Con 10 conexiones, `poll` y `epoll` empatan (1,3 µs). Con 100, `poll` tarda
7 µs, **una sola vez por vuelta del bucle**. Cualquier trabajo real de un pedido
(parsear HTTP, consultar una base de datos, leer un archivo) cuesta cientos de
microsegundos o milisegundos. Con pocas conexiones, la diferencia entre
multiplexores es ruido.

**9. ¿Cuándo no vale la pena el multiplexing?** Cuando hay **pocas conexiones
simultáneas** (decenas o algunos cientos) o cuando el trabajo por conexión es
**CPU-bound**. En la tabla de la clase 14, un thread o un proceso por cliente
funcionan bien hasta cientos de conexiones y el código es mucho más simple:
secuencial dentro de cada handler, sin máquinas de estado ni callbacks. El
multiplexing con un solo hilo además tiene su costo propio: si un handler hace
algo lento o bloqueante, **frena a todos** (ejercicio 7). El multiplexing
conviene cuando hay **miles de conexiones mayormente ociosas** y el trabajo por
evento es corto: proxies, chats, servidores de websockets, balanceadores.

## Parte D: conclusión

**10. ¿Por qué nginx puede atender más conexiones que un Apache con un thread
por cliente?**

Un Apache con un thread por cliente paga **por cada conexión abierta**, esté
activa o no: un stack de memoria por thread (del orden de MB de espacio virtual),
una entrada más para el scheduler y cambios de contexto entre miles de threads que
en su mayoría solo esperan. Con 10.000 conexiones keep-alive, son 10.000 threads
dormidos que consumen memoria para no hacer nada. nginx usa unos pocos procesos
worker (uno por núcleo), cada uno con un bucle de eventos sobre **epoll**: una
conexión ociosa le cuesta solo una entrada en el conjunto de epoll y un buffer
chico, y cada vuelta del bucle paga por las conexiones **listas**, no por las
abiertas. En mi máquina, preguntar por 5000 conexiones con 3 activas cuesta
**1,4 µs con epoll contra 1500 µs con poll**, más de 1000 veces menos. Y
`select` directamente no puede pasar de fd 1023. Así, el costo de nginx crece con
el **tráfico real** y no con la **cantidad de clientes conectados**: por eso
resolvió el problema C10K. La contra, como muestra la pregunta 7, es que cuando
casi todas las conexiones están activas a la vez, la ventaja de epoll se reduce
mucho; ahí el límite pasa a ser la CPU, no el multiplexor.

## Checklist de la consigna

- [x] Tabla con los números de mi máquina
- [x] Factor de crecimiento de `poll` (~214x para 50x conexiones)
- [x] Comportamiento de `epoll` descrito y explicado (plano, ~1,4 µs)
- [x] Dónde falla `select` y por qué (fd ≥ 1024, valor y no cantidad)
- [x] O(n) contra O(listos)
- [x] Prueba con `ACTIVOS` alto e interpretación (incluido el tope de `maxevents`)
- [x] Conclusión sobre nginx contra Apache
