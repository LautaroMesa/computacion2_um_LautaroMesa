# Clase 12 — Redes: fundamentos

Ejercicio obligatorio 6: TCP es un flujo.

## Archivos

| Archivo | Qué hace |
|---|---|
| `emisor_tcp.py` | Manda `HOLA`, `COMO`, `ESTAS` con tres `send()` separados (con `--pausa N` entre cada uno) |
| `receptor_tcp.py` | Receptor TCP que imprime **cada** `recv()` por separado (versión "con lupa" de `nc -l \| od -c`) |
| `udp_srv.py` | Receptor UDP de la consigna: imprime cada datagrama |

Agregué `receptor_tcp.py` porque `od -c` junta todo lo que recibe y no muestra
cuántas lecturas hubo. Con el receptor en Python se cuenta cuántos `recv()`
hicieron falta.

## Cómo correr

```bash
docker build -t clase12 .
docker run --rm -it --name redes clase12 bash
# dentro del contenedor, en dos terminales (la segunda con: docker exec -it redes bash)
nc -l 8080 | od -c                  # terminal 1
python emisor_tcp.py                # terminal 2

python receptor_tcp.py              # terminal 1
python emisor_tcp.py --pausa 1      # terminal 2

python udp_srv.py                   # terminal 1
python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); [s.sendto(m, ('localhost', 8080)) for m in (b'HOLA', b'COMO', b'ESTAS')]"
```

> Nota: el `nc` de OpenBSD (el de Debian/Ubuntu) **no termina** cuando el
> cliente cierra la conexión; se queda esperando EOF en su propia stdin. Hay que
> cortarlo con Ctrl+C, o en un script envolverlo con `timeout`.

## Parte A: observar el problema

### Tres `send()` seguidos, sin pausa

`nc -l 8080 | od -c` (3 de 3 corridas iguales):

```
0000000   H   O   L   A   C   O   M   O   E   S   T   A   S
0000015
```

Con `receptor_tcp.py` (5 de 5 corridas iguales):

```
recv #1: b'HOLACOMOESTAS'
TCP: 1 recv() con datos
```

**1. ¿Se distinguen los tres envíos?** No. Llegaron 13 bytes seguidos y el
receptor los leyó con **un solo** `recv()`. No hay nada en el flujo que marque
dónde terminaba cada `send()`.

### Con `sleep(1)` entre envíos

`od -c` muestra lo mismo (no puede mostrar otra cosa, porque junta todo). El
receptor en Python sí muestra la diferencia:

```
recv #1: b'HOLA'
recv #2: b'COMO'
recv #3: b'ESTAS'
TCP: 3 recv() con datos
```

**2. ¿Cambió algo? ¿Se puede confiar en eso?** Cambió: ahora cada envío llegó en su
propio `recv()`, pero es una **casualidad de la temporización**, no una garantía.
Funcionó porque el receptor ya estaba bloqueado en `recv()` cuando llegó cada
segmento y lo devolvió antes de que llegara el siguiente. En una red real, con
congestión, retransmisiones, el algoritmo de Nagle, una ventana llena o un
receptor ocupado haciendo otra cosa, los pedazos se vuelven a juntar (o se parten
en lugares arbitrarios). Además, un `sleep` de 1 s por mensaje hace inusable al
protocolo. No es una solución.

## Parte B: la pregunta

**3. Si los tres envíos llegan juntos, ¿es un bug de TCP?** No. El contrato de
TCP es entregar un **flujo de bytes** confiable y ordenado: los mismos bytes, en
el mismo orden, sin pérdidas ni duplicados. **No** promete conservar los límites
de los `send()`. `send()` significa "agregá estos bytes al flujo", y `recv(n)`
significa "dame hasta n bytes de los que haya disponibles". El kernel puede juntar
varios `send()` en un segmento o partir uno en varios, y `recv()` puede devolver
cualquier porción. Es el mismo contrato que un pipe de la clase 5.

**4. Dos formas de delimitar mensajes sobre un flujo:**

| Esquema | Cómo funciona | ¿Y si el mensaje contiene el delimitador? |
|---|---|---|
| **Delimitador** (por ejemplo `\n`) | Cada mensaje termina con un byte o secuencia reservada. El receptor acumula en un buffer y corta en cada delimitador. | El receptor lo toma como fin de mensaje y parte uno en dos. Hay que **escapar** el delimitador (como `\\n` en JSON, o *byte stuffing*) o prohibirlo en el contenido. Con datos binarios arbitrarios no sirve sin escape. |
| **Prefijo de longitud** (por ejemplo 4 bytes big-endian con el tamaño) | Antes del contenido se mandan N bytes fijos con la longitud. El receptor lee la cabecera y después exactamente esa cantidad de bytes. | No hay problema: el receptor nunca mira el contenido, solo cuenta bytes. Sirve para binario. La contra es que hay que conocer el tamaño antes de mandar, y una cabecera corrupta desincroniza todo el flujo. |

Un tercer esquema es el tamaño fijo (todos los mensajes miden lo mismo), que
solo sirve si los datos tienen tamaño fijo. HTTP combina los dos primeros:
delimitador (`\r\n\r\n`) para los headers y longitud (`Content-Length`) para el
cuerpo. En la clase 13 están implementados los dos.

## Parte C: UDP para contrastar

```
Esperando datagramas en localhost:8080 (timeout 5s)...
recv: b'HOLA' de ('127.0.0.1', 52752)
recv: b'COMO' de ('127.0.0.1', 52752)
recv: b'ESTAS' de ('127.0.0.1', 52752)
(timeout, fin)
```

**5. ¿Cuántas veces se ejecutó `recvfrom`?** Tres, una por datagrama, sin
pausas en el emisor. En TCP, el mismo envío llegó en **un** `recv()`.

**6. ¿Por qué UDP preserva los límites y TCP no?** Porque la unidad de UDP es el
**datagrama**: cada `sendto()` genera un datagrama independiente, y cada
`recvfrom()` devuelve exactamente uno entero (o nada). No hay flujo que se pueda
juntar o partir. A cambio, UDP no garantiza entrega, ni orden, ni que no haya
duplicados. TCP garantiza todo eso, y para lograrlo gestiona sus propios buffers,
segmentación y retransmisión, así que los límites de la aplicación se pierden.
Cada protocolo conserva la unidad que promete: TCP el byte, UDP el mensaje.

**7. ¿Por qué el servidor UDP no hace `listen()` ni `accept()`?** Porque UDP
**no tiene conexiones**. `listen()` prepara la cola de conexiones pendientes
(handshakes completados), y `accept()` saca una y crea un socket nuevo dedicado a
ese cliente. En UDP no hay handshake ni estado por cliente: un solo socket recibe
datagramas de cualquier origen, y `recvfrom()` devuelve junto con los datos la
dirección de quien lo mandó, para responderle con `sendto()`.

## Checklist de la consigna

- [x] Corrida donde los tres envíos llegan agrupados (`od -c` y `receptor_tcp.py`)
- [x] Por qué eso no viola el contrato de TCP
- [x] Por qué agregar `sleep` no es solución
- [x] Dos esquemas de delimitación y sus problemas
- [x] UDP preserva los límites (tres `recvfrom`)
- [x] A qué se debe la diferencia
