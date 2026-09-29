# Clase 15 — UDP

Ejercicio obligatorio 3: protocolo confiable sobre UDP.

## Archivos

| Archivo | Qué es |
|---|---|
| `perdidas.py` | El simulador de pérdidas de la cátedra (Parte A). Lo reuso por su `sendto_con_perdidas()` |
| `udp_confiable.py` | Mi implementación: servidor (en un thread) + cliente con reintentos, en dos modos: `ingenuo` y `seq` |

`udp_confiable.py` simula pérdidas **en las dos direcciones**: se puede perder el
pedido del cliente o la respuesta del servidor. El servidor cuenta cuántas veces
hizo el trabajo real, y el cliente cuenta envíos, intentos y respuestas equivocadas.

```
python3 udp_confiable.py --modo {ingenuo,seq} --perdida P [-n MENSAJES]
                         [--intentos N] [--timeout S] [--demora S] [--semilla N]
```

## Cómo correr

```bash
docker build -t clase15 .
docker run --rm clase15 python perdidas.py 0.3
docker run --rm clase15 python udp_confiable.py --modo ingenuo --perdida 0.3
docker run --rm clase15 python udp_confiable.py --modo seq --perdida 0.7 --intentos 50 --timeout 0.05
```

Las corridas de abajo usan `--semilla 1`, para que los modos `ingenuo` y `seq`
pierdan exactamente los mismos datagramas y se puedan comparar. Para las corridas
largas usé `--timeout 0.05`, porque en localhost la ida y vuelta es de microsegundos
y con 0,5 s cada pérdida cuesta medio segundo de espera (con 70% de pérdida,
la corrida pasaba de 2 minutos).

---

## Parte A: ver el problema

```
Enviados:  200
Recibidos: 139
Perdidos:  61 (30%, configurado 30%)

Primeros faltantes: [5, 8, 10, 15, 16, 17, 18, 20, 21, 22, 27, 29]
El emisor no recibió ningún error: para él, los 200 se enviaron bien.
Saltos hacia atrás en el orden de llegada: 0
```

**1.** Llegaron 139 de 200.

**2.** **Ningún** error. `sendto()` devolvió la cantidad de bytes, como si todo
hubiera salido bien. En la realidad pasa lo mismo: `sendto()` solo confirma que el
datagrama salió de la interfaz local. Lo que pase después en la red, el emisor
no lo ve.

**3.** *UDP entrega cada datagrama entero o no lo entrega, sin avisar nunca si
se perdió: si hace falta confiabilidad, la tiene que agregar la aplicación.*

**3b. (`tc netem`)** No lo pude correr: en mi WSL `sudo` pide contraseña y la
prueba era desatendida. Lo que se esperaría con `reorder 25% 50%`: "Saltos hacia
atrás" deja de ser 0, porque algunos datagramas llegan antes que otros enviados
antes. Un protocolo que suponga orden (por ejemplo, "el mensaje 5 viene después
del 4") procesaría datos en el orden equivocado o interpretaría un faltante
como pérdida cuando solo está demorado. Por eso los números de secuencia sirven
también para reordenar, no solo para deduplicar.

## Parte B: retransmisión

`pedir_con_reintentos()` manda el pedido, espera con `settimeout()` y, si salta
`TimeoutError`, lo vuelve a mandar, hasta `intentos` veces.

### 4. Con 30% de pérdida

```
modo=ingenuo  perdida=30% por direccion  timeout=0.05s  intentos max=10
  Mensajes:                     50
  Con respuesta:                50  (sin respuesta tras 10 intentos: 0)
  Envios reales del cliente:    102
  Intentos promedio (exitosos): 2.04  (maximo 6)
```

**2,04 intentos** en promedio. Coincide con la teoría: un intento sale bien si
no se pierde ni el pedido ni la respuesta, con probabilidad 0,7 × 0,7 = 0,49. El
número esperado de intentos es 1 / 0,49 = **2,04**.

### 5. Con 70% de pérdida

Cada intento sale bien con probabilidad 0,3 × 0,3 = **0,09**.

| Intentos máx. | Con respuesta | Teoría: 1 − 0,91ⁿ | Intentos promedio |
|---|---|---|---|
| 10 | 33 de 50 (66%) | 61% | 4,73 |
| 50 | **50 de 50** | 99% | 9,30 (máximo 33) |

Con el límite de 5 que sugiere la consigna, solo el 38% de los mensajes tendría
respuesta. Para que funcione al 70% hay que subir los intentos: con 50, llegaron
todos. Cuesta ~9 envíos por mensaje, y alguno necesitó 33.

### 6. Timeout muy corto y muy largo

**Muy largo (5 s, 10 mensajes):** 10 de 10 con respuesta, pero en **85,67 s**:
cada pérdida cuesta 5 s de espera, aunque la respuesta real tarde microsegundos.
Es correcto pero lentísimo.

**Muy corto (0,01 s, con un servidor que tarda 0,02 s en responder):**

```
modo=ingenuo  perdida=30% por direccion  timeout=0.01s  intentos max=10
  Envios reales del cliente:    143
  Veces que el servidor hizo el trabajo:  75
  Respuestas equivocadas aceptadas:       47
```

El cliente reintenta **antes** de que la respuesta pudiera llegar. Eso genera
envíos y trabajo de más, y además **47 de 50 respuestas aceptadas eran de otro
mensaje**: la respuesta atrasada del mensaje `i` llega mientras el cliente ya
espera la del `i+1`, y la toma como propia. El timeout tiene que ser algo mayor
que el tiempo de ida y vuelta real. TCP lo calcula dinámicamente midiendo el RTT.

## Parte C: el problema del duplicado

**7.** No lo puede saber. Desde el cliente, "se perdió mi pedido" y "se perdió la
respuesta" se ven igual: no llega nada antes del timeout.

**8.** En el segundo caso el servidor **ya hizo el trabajo**, y el reintento se lo
hace repetir. El servidor de `udp_confiable.py` cuenta cuántas veces trabajó:

| Corrida (modo ingenuo) | Mensajes | Veces que trabajó | De más |
|---|---|---|---|
| 30% de pérdida | 50 | 63 | +13 |
| 70% de pérdida, 50 intentos | 50 | 136 | **+86** |

**9.** Poner algo en mayúsculas dos veces da el mismo resultado: es
**idempotente**. "Transferir $100" no lo es: cada repetición mueve plata otra vez.
Con 70% de pérdida, el servidor habría hecho 136 transferencias para 50 pedidos.

## Parte D: números de secuencia

Cada mensaje lleva adelante `struct.pack('!I', seq)`.

- **Servidor (10):** guarda la respuesta de cada `(cliente, seq)`. Si llega un
  duplicado, **reenvía la respuesta guardada** sin volver a trabajar.
- **Cliente (11):** descarta las respuestas cuyo `seq` no es el del pedido en curso
  y sigue esperando hasta completar el timeout de ese intento.

Mismas pérdidas que antes (misma semilla):

| Corrida | Modo | Datagramas al servidor | Veces que trabajó | Respuestas equivocadas |
|---|---|---|---|---|
| 30% | ingenuo | 63 | 63 | 0 |
| 30% | **seq** | 63 | **50** | 0 |
| 70%, 50 intentos | ingenuo | 136 | 136 | 0 |
| 70%, 50 intentos | **seq** | 136 | **50** | 0 |
| timeout 0,01 | ingenuo | 75 | 75 | **47** |
| timeout 0,01 | **seq** | 100 | **50** | **0** (20 viejas descartadas) |

**10.** Con deduplicación, el servidor trabaja **exactamente 50 veces**, una
por mensaje, aunque le lleguen 136 datagramas.

**11. ¿Por qué el cliente tiene que descartar por seq?** Por las respuestas
**demoradas**. Si el intento 1 de `seq=7` se atrasa (no se pierde), el cliente
reintenta, recibe la respuesta del intento 2 y pasa a `seq=8`. Después llega la
respuesta atrasada de `seq=7`: sin chequear el seq, el cliente la tomaría como
respuesta de `seq=8`. Es exactamente lo que pasó en la corrida con timeout 0,01:
**47 respuestas equivocadas en modo ingenuo, 0 con seq**.

**12. Comparación con `confiable.py` (con 0.6):**

```
Mensajes enviados por la app:      5
Envíos reales (con reintentos):    15
Veces que el servidor hizo trabajo: 5
```

Es la misma idea: 15 envíos reales y 5 trabajos. Mi versión además mide el modo
sin deduplicar con las mismas pérdidas, para ver la diferencia en el mismo
experimento, y agrega el caso de las respuestas atrasadas.

## Parte E: reflexión

**13. Garantías de TCP que mi implementación todavía no tiene:**

1. **Control de flujo y de congestión.** Mando al ritmo que quiero. TCP ajusta la
   velocidad según lo que el receptor puede absorber (ventana) y según la
   congestión de la red, y baja la tasa cuando detecta pérdidas. Mi cliente
   reintenta igual aunque la red esté saturada, y así la empeora.
2. **Más de un mensaje en vuelo (ventana deslizante).** Es *stop-and-wait*: un
   mensaje por vez, esperando su respuesta. Con un RTT de 100 ms eso son 10
   mensajes por segundo como máximo. TCP mantiene muchos segmentos sin confirmar
   a la vez.
3. **Timeout adaptativo.** El timeout es fijo. TCP mide el RTT y calcula el RTO
   (con backoff exponencial en cada reintento); la Parte B6 muestra qué pasa con
   un timeout mal elegido.
4. **Conexión y memoria acotada.** No hay handshake ni cierre. El servidor guarda
   las respuestas de **todos** los seq para siempre (la memoria crece sin límite),
   y si el cliente se reinicia y vuelve a empezar desde `seq=0`, el servidor le
   devuelve respuestas viejas. TCP negocia números de secuencia iniciales al
   conectar y libera el estado al cerrar.
5. Tampoco hay entrega **ordenada** de un flujo (solo funciona porque hay un
   mensaje por vez) ni **mensajes más grandes que un datagrama**.

**14. ¿Cuándo dejar de agregar confiabilidad sobre UDP y usar TCP?** Cuando se
necesitan **todas** las garantías: que llegue todo, en orden, sin duplicados, con
control de congestión. A esa altura estaría reimplementando TCP, peor y con más
bugs. UDP con confiabilidad propia conviene cuando se quiere **solo una parte**:
juegos o VoIP, donde un dato viejo ya no sirve y conviene descartarlo antes que
retransmitirlo; DNS, con un pedido y una respuesta cortos sin gastar un handshake;
o cuando se quiere controlar la retransmisión uno mismo (QUIC, que además evita que
una pérdida trabe todos los flujos, como pasa en TCP).

## Checklist de la consigna

- [x] Cliente que reintenta con timeout
- [x] Funciona con 70% de pérdida (en cada dirección), con suficientes intentos
- [x] Servidor que cuenta las veces que hace el trabajo real
- [x] Sin deduplicación el servidor procesa de más (63/50 y 136/50)
- [x] Números de secuencia con `struct.pack('!I', ...)`
- [x] Servidor que deduplica y reenvía la respuesta guardada
- [x] Cliente que descarta respuestas con `seq` incorrecto
- [x] Garantías de TCP que faltan
