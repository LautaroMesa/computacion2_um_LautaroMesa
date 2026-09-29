# Clase 19 — HTTP + FastAPI

Ejercicio obligatorio 3: una API con FastAPI.

## Archivos

| Archivo | Qué es |
|---|---|
| `api.py` | El `api.py` de la cátedra, extendido con `PATCH /tareas/{id}`, `GET /estadisticas`, el límite de 10 pendientes y un `print` para ver cuándo corre `crear()` |
| `tipos_importan.py` | Parte D: apps mínimas con y sin anotaciones, probadas con `TestClient` |
| `requirements.txt` | `fastapi`, `uvicorn`, `httpx` |

## Cómo correr

```bash
docker build -t clase19 .
docker run --rm -p 8000:8000 clase19                  # http://localhost:8000/docs
docker run --rm clase19 python tipos_importan.py
```

Sin Docker: `pip install -r requirements.txt && python3 api.py`.

Versiones con las que lo probé: FastAPI 0.141, Pydantic 2.13, uvicorn 0.54 (en Windows).

---

## Parte A: lo mínimo

**1. ¿Quién escribió la documentación de `/docs`?** Nadie a mano: **FastAPI la
genera** leyendo el código. Toma las rutas y los métodos de los decoradores, los
parámetros y sus tipos de las firmas de las funciones, los cuerpos y sus
restricciones de los modelos Pydantic (`Literal`, `ge=1, le=5`), los textos de los
docstrings y `description=`, y los códigos de respuesta de `status_code=` y
`responses=`. La página es Swagger UI, que dibuja esa información.

**2.** Mandar un `tipo` que no está en la lista (desde `/docs` o con curl)
devuelve **422** y el mensaje dice cuáles son los válidos (ver la Parte B). En
`/docs` el campo ya aparece como un enum con los tres valores posibles.

**3. `/openapi.json`** es la **especificación OpenAPI** (antes llamada Swagger)
de la API: un JSON estándar que describe todas las rutas, parámetros, esquemas de
los cuerpos y respuestas. `/docs` se dibuja a partir de ese archivo, y lo pueden
usar otras herramientas: generadores de clientes en otros lenguajes, Postman,
tests de contrato.

## Parte B: la validación

**4.** Los cuatro errores:

| Pedido | Código | Mensaje |
|---|---|---|
| `GET /tareas/abc` | **422** | `loc: ["path","tarea_id"]` — *Input should be a valid integer, unable to parse string as an integer* |
| `POST {"tipo":"volar"}` | **422** | `loc: ["body","tipo"]` — *Input should be 'descargar', 'hashear' or 'esperar'* |
| `POST {"tipo":"esperar","prioridad":99}` | **422** | `loc: ["body","prioridad"]` — *Input should be less than or equal to 5* |
| `GET /tareas/999` | **404** | `{"detail":"No existe esa tarea"}` |

**5. 422 contra 404.** Los tres primeros dan **422 Unprocessable Entity**: el
pedido está **mal formado** respecto de lo que la API acepta (un id que no es
entero, un tipo fuera de la lista, una prioridad fuera de rango). Lo detecta
FastAPI **antes** de llamar a mi función, sin mirar los datos. El último da **404
Not Found**: el pedido es **válido** (999 es un entero), pero el recurso no
existe. Eso solo lo puede saber mi función, buscando en `tareas`, y por eso lo
lanza ella con `HTTPException(404)`. En resumen: 422 es "tu pedido está mal
armado"; 404 es "está bien armado, pero lo que buscás no está".

**6. El campo `loc`** dice **dónde** está el error: la primera parte es la
**sección del pedido** (`path`, `query`, `body`, `header`) y las siguientes son el
camino hasta el campo (`["body","prioridad"]`). Con un modelo anidado sería algo
como `["body","opciones","reintentos"]`. Sirve para que un cliente (o un
formulario) marque exactamente el campo que falló.

**7. ¿Antes o después de mi función?** **Antes.** `crear()` tiene un
`print('crear() ejecutandose ...')`. En el log del servidor, los POST que dieron
422 **no** tienen el print; los que dieron 201 sí:

```
INFO:     127.0.0.1:54767 - "POST /tareas HTTP/1.1" 422 Unprocessable Entity
INFO:     127.0.0.1:54769 - "POST /tareas HTTP/1.1" 422 Unprocessable Entity
INFO:     127.0.0.1:54771 - "GET /tareas/999 HTTP/1.1" 404 Not Found
crear() ejecutandose con TareaNueva(tipo='descargar', prioridad=3)
INFO:     127.0.0.1:54773 - "POST /tareas HTTP/1.1" 201 Created
```

FastAPI parsea el JSON y lo valida con Pydantic; si falla, responde 422 él mismo.
Mi función solo recibe objetos que ya son válidos.

## Parte C: agregar endpoints

### 8. `PATCH /tareas/{id}`

```python
class TareaCambios(BaseModel):
    estado: Estado | None = None
    prioridad: int | None = Field(default=None, ge=1, le=5)

@app.patch('/tareas/{tarea_id}', response_model=Tarea)
async def modificar(tarea_id: int, cambios: TareaCambios):
    ...
    tareas[tarea_id].update(cambios.model_dump(exclude_unset=True))
```

Todos los campos son opcionales, y con `exclude_unset=True` solo se aplican los
que el cliente **mandó**. Sin eso, un PATCH con solo `estado` pisaría la
prioridad con `None`. (La consigna pide cambiar el estado; dejé también la
prioridad porque es el uso normal de un PATCH y no cuesta nada).

```
PATCH /tareas/1   {"estado":"ejecutando"}  -> 200 {"tipo":"descargar","prioridad":3,"id":1,"estado":"ejecutando"}
PATCH /tareas/1   {"estado":"volando"}     -> 422 loc ["body","estado"]: Input should be 'pendiente', 'ejecutando' or 'completada'
PATCH /tareas/999 {"estado":"completada"}  -> 404 No existe esa tarea
```

La prioridad quedó en 3: el PATCH solo tocó el estado.

### 9. `GET /estadisticas`

```
{"total":11,"por_estado":{"pendiente":10,"ejecutando":1,"completada":0}}
```

Siempre devuelve los tres estados, aunque tengan 0, para que el cliente no tenga
que tratar la ausencia de una clave como caso especial.

### 10. Límite de 10 pendientes: **503 Service Unavailable**

```
201 201 201 201 201 201 201 201 201 201 503

HTTP/1.1 503 Service Unavailable
retry-after: 5
{"detail":"Hay 10 tareas pendientes (maximo 10); reintentar mas tarde"}
```

(La primera tarea ya estaba en `ejecutando`, así que entran 10 más y la 11.ª
rebota).

**Por qué 503:** la situación es una **sobrecarga temporal del servidor**: la
cola está llena. El pedido del cliente es correcto y va a funcionar más tarde,
cuando se procesen tareas. 503 dice exactamente eso ("no puedo atenderte
**ahora**"), y el header `Retry-After` le indica al cliente cuándo reintentar.
Las alternativas que descarté:
- **422 / 400**: son para pedidos inválidos, y este no lo es. El cliente no tiene
  nada que corregir.
- **429 Too Many Requests**: es para cuando **un cliente** excede su cuota
  (rate limiting). Acá la cola es global: un cliente que manda su primera tarea
  también rebota por culpa de los demás.
- **409 Conflict**: es un conflicto con el estado del recurso (por ejemplo, una
  versión desactualizada). Se podría argumentar, pero no transmite que es
  temporal ni permite `Retry-After`.

## Parte D: los tipos importan

Salida de `tipos_importan.py`:

```
== obtener(tarea_id: int)
  GET /tareas/abc -> 422 ["['path', 'tarea_id']: Input should be a valid integer, ..."]
  GET /tareas/1 -> 200 {'recibido': '1', 'id': 1, 'tipo': 'esperar'}

== obtener(tarea_id)
  GET /tareas/abc -> 404 {'detail': "No existe esa tarea (busque 'abc')"}
  GET /tareas/1 -> 404 {'detail': "No existe esa tarea (busque '1')"}
```

**11. Sin `: int`**, `/tareas/abc` pasa de **422 a 404**: FastAPI ya no valida,
así que `'abc'` llega a la función como `str` y la búsqueda falla. Peor: **ahora
`/tareas/1` también da 404**, aunque la tarea 1 existe. Sin la anotación, el
parámetro llega como el string `'1'`, y `'1' in {1: ...}` es `False`. La
anotación no solo valida: **convierte**.

```
== prioridad: str
  json={'prioridad': 3}         -> 422 Input should be a valid string
  json={'prioridad': '3'}       -> 200 {'prioridad': '3', ...}
  json={'prioridad': 'urgente'} -> 200 {'prioridad': 'urgente', ...}
  json={'prioridad': 2.5}       -> 422 Input should be a valid string
```

**12. Con `prioridad: str`**, acepta **cualquier texto** (`"urgente"`, `"3"`),
porque se pierde la noción de número y de rango. Y lo inesperado: **rechaza el
número `3`**. Pydantic v2 no convierte números a string (en v1 sí lo hacía), así
que un cliente que mandaba `{"prioridad": 3}` y funcionaba pasa a recibir 422.
Cambiar el tipo cambió el contrato de la API en las dos direcciones.

En cambio, con `int`, Pydantic en modo *lax* acepta `"3"` → `3`, `2.0` → `2` y
**`true` → `1`**, y rechaza `2.5` y `"urgente"`. Si hace falta que solo acepte
enteros JSON de verdad, se puede usar `Field(strict=True)`.

**13. Las tres cosas que hace FastAPI con cada anotación:**
1. **Valida**: si el dato no cumple el tipo y las restricciones, responde 422
   sin llamar a la función.
2. **Convierte**: transforma lo que llega (texto en la URL, JSON) al tipo de
   Python declarado (`'1'` → `1`, un dict → un objeto `TareaNueva`).
3. **Documenta**: lo incluye en el esquema OpenAPI, así que aparece en
   `/openapi.json` y `/docs`.

Además, `response_model` hace lo mismo con la **salida**: filtra y valida lo que
devuelve la función.

## Checklist de la consigna

- [x] La API levanta y `/docs` funciona (200)
- [x] Los cuatro errores provocados, con código y mensaje
- [x] Diferencia entre 422 y 404
- [x] La validación ocurre antes de la función (log con `print`)
- [x] `PATCH /tareas/{id}` con un modelo de campos opcionales
- [x] `GET /estadisticas`
- [x] Código para el límite de pendientes justificado (503 + `Retry-After`)
- [x] Qué hace FastAPI con las anotaciones de tipo
