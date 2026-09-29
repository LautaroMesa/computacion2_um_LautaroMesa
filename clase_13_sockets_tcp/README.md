# Clase 13 — Sockets TCP

Ejercicio obligatorio 3: framing.

## Archivos

| Archivo | Qué hace |
|---|---|
| `servidor_lineas.py` | Framing por delimitador: `recibir_lineas()` (generador con buffer) y respuesta en mayúsculas. Puerto 8080 |
| `servidor_longitud.py` | Framing por longitud: `recibir_exacto()`, `enviar_mensaje()`, `recibir_mensaje()` con cabecera `!I`. Puerto 8081 |
| `probar_framing.py` | Cliente que prueba los dos servidores en los casos extremos y dice OK/FALLA en cada uno |

## Cómo correr

```bash
docker build -t clase13 .
docker run --rm -it --name framing clase13 bash
python servidor_lineas.py &          # 8080
python servidor_longitud.py &        # 8081
python probar_framing.py
nc localhost 8080                    # probar a mano: escribir líneas
```

## Parte A: el problema

Con `echo_server.py` y `echo_client.py --tres` del repo de la cátedra (3 corridas, todas iguales):

```
Conexión desde ('127.0.0.1', 42036)
  [127.0.0.1:42036] recv 13 bytes: b'HOLACOMOESTAS'
  [127.0.0.1:42036] cerró tras 13 bytes
```

**1.** El cliente hizo tres `sendall()` y el servidor hizo **un solo** `recv()`,
que trajo los 13 bytes juntos (`recv 13 bytes: b'HOLACOMOESTAS'`).

**2.** No viola el contrato: TCP garantiza los mismos bytes, en orden y sin
pérdidas, pero no conserva los límites de cada `send()` (ver clase 12). Separar
los mensajes le toca a la aplicación.

## Partes B y C: resultados de `probar_framing.py`

```
Delimitador (\n) -> localhost:8080
  [OK   ] todo junto en un sendall()
          respuestas: [b'UNO', b'DOS', b'TRES']
  [OK   ] byte por byte (sleep 0.2)
          respuestas: [b'HOLA']
  [LIMIT] mensaje con \n adentro (se espera 1 respuesta)
          respuestas: [b'LINEA1', b'LINEA2']
          esperadas:  [b'LINEA1\nLINEA2']

Longitud (4 bytes !I) -> localhost:8081
  [OK   ] todo junto en un sendall()
          respuestas: [b'UNO', b'DOS', b'TRES']
  [OK   ] byte por byte, cabecera incluida (sleep 0.05)
          respuestas: [b'HOLA']
  [OK   ] mensaje con \n adentro
          respuestas: [b'LINEA1\nLINEA2']
  [OK   ] mensaje vacio (y uno despues)
          respuestas: [b'', b'DESPUES DEL VACIO']
  [OK   ] binario (los 256 valores de byte)
          respuestas: [b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0...]
```

**3.** Con `nc localhost 8080`, cada línea que escribo vuelve en mayúsculas.

**4.** `b'uno\ndos\ntres\n'` en un solo `sendall()` → tres respuestas. El
`while DELIM in buffer` interno entrega **todas** las líneas completas que
haya en el buffer, no solo la primera.

**5.** `hola\n` byte por byte → una respuesta. Los primeros 4 `recv()` traen un
byte cada uno y quedan en el buffer; recién con el `\n` se completa la línea.
Del lado de longitud, la prueba equivalente manda **hasta la cabecera** de a un
byte: `recibir_exacto(sock, 4)` junta los 4 bytes en 4 vueltas.

**6. ¿Por qué `recibir_exacto()` no puede ser `return sock.recv(n)`?** Porque
`recv(n)` devuelve **hasta** n bytes, lo que haya en el buffer del kernel en
ese momento. Si la cabecera llega partida, `recv(4)` puede devolver 2 bytes;
`unpack` falla, o peor, los 2 bytes que faltan se leen como parte del payload y
todo el flujo queda desincronizado para siempre. Hay que insistir en un bucle
hasta completar n, y devolver `None` si `recv` devuelve `b''` (el otro lado cerró).

**7. Mensaje con `\n` adentro.** Con longitud funciona: el receptor nunca mira
el contenido, solo cuenta bytes. Con delimitador, `b'linea1\nlinea2'` llega como
**dos** mensajes: el servidor no puede distinguir el `\n` del contenido del `\n`
que cierra el mensaje. Para arreglarlo habría que escapar el contenido (por
ejemplo, mandar JSON, que codifica el `\n` como `\\n`).

**8. Mensaje de 0 bytes y de 5 GB.**
- **0 bytes**: es válido, se manda solo la cabecera `00 00 00 00`. Hay que
  distinguir el mensaje vacío (`b''`) del cierre de conexión (`None`). Por eso
  `recibir_mensaje` devuelve cosas distintas y no usa `if not mensaje`. La prueba
  manda uno vacío y otro después para comprobar que el flujo no se desincroniza.
- **5 GB**: no entra. `!I` es un entero sin signo de 32 bits, así que el máximo
  es 2³² − 1 ≈ 4 GB y `struct.pack` tira `struct.error`. Para mensajes más grandes
  habría que usar `!Q` (64 bits). Aunque entrara, el receptor intentaría juntar 5 GB
  en memoria porque lo dice la cabecera, y esa cabecera la controla el cliente (o
  una trama corrupta). Por eso `servidor_longitud.py` rechaza todo lo que supere
  `MAX_MENSAJE` (16 MB) y corta la conexión. Lo mismo vale para el delimitador:
  un cliente que nunca manda `\n` hace crecer el buffer sin límite, así que
  `servidor_lineas.py` corta pasados los 64 KB.

## Parte D: comparación

**9.**

| | Delimitador | Longitud |
|---|---|---|
| Contenido binario arbitrario | No (el delimitador puede aparecer en los datos; hay que escapar) | Sí |
| Depurable con `nc` | Sí, es texto y se escribe a mano | No, hay que escribir la cabecera binaria (con `printf '\x00\x00\x00\x04hola'`) |
| Hay que saber el tamaño antes | No, se puede ir mandando y cerrar con el delimitador | Sí, la cabecera va primero |

**10. ¿Por qué HTTP usa delimitador para los headers y longitud para el cuerpo?**
Los headers son texto, cortos y de tamaño desconocido al empezar a escribirlos.
El delimitador (`\r\n` por header, `\r\n\r\n` al final) los hace legibles y
depurables con `nc` o `telnet`. El cuerpo, en cambio, puede ser **binario**
(imágenes, archivos comprimidos), donde cualquier secuencia de bytes puede
aparecer, y puede ser grande. Ahí sirve la longitud (`Content-Length`): el
receptor lee exactamente esa cantidad sin mirar el contenido. Cuando el tamaño no
se sabe de antemano (contenido generado al vuelo), HTTP/1.1 usa `chunked`: una
serie de bloques, cada uno con su longitud, que combina las dos ideas.

## Comparación con `framing.py` de la cátedra

Las mismas funciones con la misma lógica: buffer que sobrevive entre `recv()`,
bucle `while` para entregar todas las líneas completas, y `recibir_exacto` en
bucle. Las diferencias de mi versión:

- **Topes** (`MAX_LINEA`, `MAX_MENSAJE`) para que un cliente no pueda hacer
  crecer la memoria del servidor sin límite.
- **Cierre a mitad de mensaje**: si llega la cabecera pero la conexión se cierra
  antes del payload, lanzo `ConnectionResetError` en lugar de devolver `None`, que
  se confundiría con un cierre prolijo entre mensajes.
- `recibir_exacto` junta en una lista y hace un `join` al final, en lugar de
  `datos += pedazo`, para no copiar el buffer entero en cada vuelta cuando el
  mensaje es grande.

## Checklist de la consigna

- [x] Framing por delimitador funcionando
- [x] Framing por longitud funcionando
- [x] Ambos sobreviven a todos los mensajes en un solo `sendall()`
- [x] Ambos sobreviven a un mensaje byte por byte
- [x] `recibir_exacto()` con bucle
- [x] Longitud maneja contenido con `\n` adentro (y binario arbitrario)
- [x] Cierre de conexión (`recv()` → `b''`) manejado en los dos
