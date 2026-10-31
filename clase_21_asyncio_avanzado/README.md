# Clase 21 — Asyncio avanzado

Ejercicio obligatorio 3: sacar el trabajo del loop.

## Archivos

| Archivo | Qué es |
|---|---|
| `executor.py` | El de la cátedra (partes A y B): mide el atraso del loop sin executor, con proceso y con thread, y `--paralelo` con 4 tareas |
| `executor_extra.py` | Lo mío para las preguntas 7-10: `uno` (una sola tarea), `io` (con `time.sleep`), `lambda` (el error de pickle) y `grande` (costo de mandar una lista de un millón) |
| `api.py` | La API de la clase 19 con `POST /hashear?modo=directo\|executor` y el `ProcessPoolExecutor` creado en el `lifespan` (parte D) |
| `medir_api.py` | Manda un `POST /hashear` y mide `GET /tareas` cada 100 ms mientras se calcula |

## Cómo correr

```bash
docker build -t clase21 .
docker run --rm clase21 python executor.py
docker run --rm clase21 python executor.py --paralelo
docker run --rm clase21 python executor_extra.py uno      # también: io, lambda, grande

# Parte D: la API en un contenedor y la medición en otro proceso del mismo
docker run -d --name api21 clase21
docker exec api21 python medir_api.py directo
docker exec api21 python medir_api.py executor
docker rm -f api21
```

Todo corrió en Ubuntu 24.04 (WSL2), Python 3.12, 16 CPUs. En mi máquina las
3.000.000 de vueltas de `hashear` tardan ~1,4 s, no los ~5 s que dice el
comentario del script: los números absolutos son más chicos, pero las
proporciones son las mismas.

---

## Parte A: el loop bloqueado

```
Un cálculo de ~5s, y cuánto se atrasa el event loop mientras tanto:

  sin executor                      1.38s  |  peor atraso:   1380.9 ms
  con ProcessPoolExecutor           1.37s  |  peor atraso:      5.4 ms
  con asyncio.to_thread             1.34s  |  peor atraso:      6.6 ms
```

**1.** Tiempos: 1,38 s / 1,37 s / 1,34 s. Peor atraso: 1380,9 ms / 5,4 ms / 6,6 ms.

**2. ¿Cuánto se atrasa el loop sin executor?** 1381 ms, o sea **todo** lo que
dura el cálculo (1,38 s). El medidor pidió despertarse a los 50 ms y se despertó
casi un segundo y medio después, porque `hashear()` no tiene ningún `await`: el
loop no recupera el control hasta que termina. Para un servidor significa que
durante ese tiempo **no atiende a nadie**: no acepta conexiones, no responde
pedidos (ni siquiera un `GET` trivial), no dispara timeouts, no manda los
heartbeats de un WebSocket. Si el cálculo durara 30 s, el balanceador de carga
lo daría por muerto.

**3. Con executor el trabajo tarda lo mismo. ¿Qué mejoró?** No mejoró el
cálculo: mejoró **todo lo demás**. El atraso pasó de 1381 ms a 5 ms: el loop
quedó libre mientras otro proceso (o thread) calculaba, y siguió atendiendo
otras corrutinas. Lo que se gana no es *throughput* de esa tarea sino
**latencia del resto del sistema**. El `await` del `run_in_executor` deja a esa
corrutina esperando como si fuera I/O, y el loop sigue con las demás.

**4. ¿Por qué mide el atraso de un `sleep`?** Porque `asyncio.sleep(0.05)` es
la forma más pura de preguntarle al loop "¿me podés despertar en 50 ms?".
Despertar una corrutina dormida es exactamente el trabajo del loop: si se
atrasa, es porque el loop estaba ocupado con otra cosa. Medir el `sleep` aísla
el estado del loop del costo de cualquier otra operación (red, disco). Es la
misma idea que `loop.slow_callback_duration` del modo debug, o la "event loop
lag" de Node.js.

## Parte B: threads contra procesos

```
4 tareas CPU-bound simultáneas:

  asyncio.to_thread (threads)       5.84s
  ProcessPoolExecutor (procesos)    1.99s

  Diferencia: 2.9x
```

**5.** Con 4 tareas: **5,84 s con threads, 1,99 s con procesos**.

**6. ¿Por qué la diferencia?** Por el **GIL** (clase 10). Los 4 threads
existen, pero solo uno a la vez puede ejecutar bytecode de Python, así que se
turnan: 4 × 1,3 s ≈ 5,2 s, más el costo de los cambios de turno, da 5,84 s. Con
procesos, cada uno tiene **su propio intérprete y su propio GIL**: los 4
corren de verdad en paralelo en 4 núcleos y tardan lo que tarda uno (más el
arranque del pool). No es 4x exacto por el costo de crear los procesos y
porque `hashlib.sha256` sobre 1 byte es tan corto que el GIL casi nunca se
suelta durante el hash.

**7. Con una sola tarea empatan.**

```
1 sola tarea CPU-bound:

  asyncio.to_thread (threads)       1.30s
  ProcessPoolExecutor (procesos)    1.28s
```

El GIL solo se nota cuando hay **varios threads queriendo ejecutar Python al
mismo tiempo**. Con uno solo, no tiene con quién competir: el thread del
cálculo tiene el GIL casi todo el tiempo, y el thread del loop lo pide solo un
instante cada 50 ms (para eso está el intervalo de switch de 5 ms,
`sys.getswitchinterval()`). Por eso el loop sigue respondiendo con threads
(atraso de 6,6 ms en la parte A) aunque el GIL exista.

**8. Con trabajo I/O-bound (`time.sleep(2)`):**

```
4 tareas con time.sleep(2):

  asyncio.to_thread (threads)       2.00s
  ProcessPoolExecutor (procesos)    2.00s
```

**Ya no se diferencian.** `time.sleep` (como `read`, `recv`, etc.) **suelta el
GIL** mientras espera: los 4 threads duermen al mismo tiempo. Para I/O
bloqueante, los threads alcanzan y son más baratos (no hay que crear
procesos ni serializar argumentos). La regla queda: **CPU-bound → procesos,
I/O bloqueante → threads**, y I/O con librerías async → ni uno ni otro, `await`
directo.

## Parte C: el costo de los procesos

**9. Pasarle una `lambda` al `ProcessPoolExecutor`:**

```
  builtins.AttributeError: Can't pickle local object 'con_lambda.<locals>.<lambda>'
  la misma lambda con asyncio.to_thread devuelve: 4
```

Para mandar trabajo a otro proceso, el pool **serializa con `pickle`** la
función y sus argumentos y los manda por un pipe (clase 5). `pickle` no
serializa el código de una función: guarda **su nombre** (`modulo.funcion`) y
el otro proceso la busca importando el módulo. Una `lambda` (o una función
definida dentro de otra) no tiene un nombre importable, así que no se puede
picklear. Con un thread anda porque comparte la memoria: no hay nada que
mandar. Por eso en el TP2 `sha256_iterado` está a nivel de módulo en `cpu.py`.

**10. Argumento grande contra un número:**

```
  un número                0.55 ms por llamada
  lista de 1.000.000      71.51 ms por llamada
  (thread, la lista)       0.27 ms por llamada
```

Mandar una lista de un millón cuesta **~130 veces más** que un número, y la
función no hace casi nada (`len`). Todo ese tiempo es pickle de ida, el pipe,
unpickle del otro lado (y el resultado de vuelta). Con un thread la misma lista
cuesta 0,27 ms porque se pasa **la referencia**, no una copia. Conclusión: a un
proceso hay que mandarle **poco** (una ruta, un rango, una semilla) y que
genere o lea los datos allá, o usar memoria compartida (clase 7).

**11. ¿Por qué crear el pool una vez y no por tarea?** Porque crear un proceso
cuesta: `fork`/`spawn`, arrancar un intérprete, importar módulos (en Windows y
macOS con `spawn` son decenas de ms o más). Si se crea por tarea, ese costo se
paga cada vez y para tareas cortas domina. Creado una vez en el arranque, los
procesos quedan vivos esperando trabajo y cada tarea paga solo el viaje del
pickle. Es lo que hace el `lifespan` de `api.py` (y el TP2, que además lo
"precalienta" con una tarea vacía para que el primer pedido no pague el
arranque).

## Parte D: en una API

**12.** `api.py` es la API de la clase 19 con un endpoint nuevo:

```python
@app.post('/hashear')
async def hashear_endpoint(modo: Literal['directo', 'executor'] = 'executor'):
    if modo == 'directo':
        resultado = hashear()          # congela el event loop todo el calculo
    else:
        loop = asyncio.get_running_loop()
        resultado = await loop.run_in_executor(app.state.pool, hashear)
```

y el pool creado en el `lifespan`:

```python
@asynccontextmanager
async def ciclo(app: FastAPI):
    app.state.pool = ProcessPoolExecutor(max_workers=2)
    yield
    app.state.pool.shutdown(cancel_futures=True)
```

**13 y 14. `GET /tareas` mientras procesa:**

```
--- sin servidor ocupado:
0.001997s
0.001498s
0.001192s
modo=directo: el hash tardó 1.98 s
  GET /tareas durante el cálculo: 1 pedidos, mediana 1656.3 ms, peor 1656.3 ms
modo=executor: el hash tardó 1.56 s
  GET /tareas durante el cálculo: 12 pedidos, mediana 2.8 ms, peor 9.7 ms
--- con curl, como pide la consigna (otra terminal):
GET /tareas durante directo: 1.066484s
GET /tareas durante executor: 0.001211s
```

Sin executor, `GET /tareas` (que normalmente tarda 1-2 ms) tardó **1656 ms**:
el pedido llegó, pero el loop no lo pudo leer hasta que terminó el hash. En
todo el cálculo entró **un solo** pedido. Con executor tardó **2,8 ms de
mediana (peor 9,7 ms)** y se atendieron 12 pedidos mientras el hash corría en
otro proceso.

**15. Medición 2 del TP2:** sin executor **~1660 ms**, con executor **~3 ms**.
Es la misma diferencia que mido en el TP2 (`Carpeta-Tp2/`, medición 2), donde
sin executor da 3007 ms porque ahí el hash es más largo.

---

## Verificación

- [x] Los tres tiempos y los tres atrasos, con números propios
- [x] Qué significa el atraso para un servidor (pregunta 2)
- [x] Qué mejora el executor si el trabajo tarda lo mismo (pregunta 3)
- [x] Threads contra procesos con 4 tareas CPU-bound (pregunta 5)
- [x] La diferencia explicada con el GIL (pregunta 6)
- [x] Una tarea sola: empatan y por qué (pregunta 7)
- [x] El error de pasar una lambda (pregunta 9)
- [x] La medición en una API real (parte D)
