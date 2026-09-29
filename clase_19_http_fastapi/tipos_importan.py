#!/usr/bin/env python3
"""Parte D: que pasa al sacar o cambiar las anotaciones de tipo.

Arma apps minimas con y sin `: int`, y con prioridad int o str, y les hace
pedidos con TestClient (no hace falta levantar el servidor).

Uso:
    pip install -r requirements.txt
    python3 tipos_importan.py
"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

TAREAS = {1: {'id': 1, 'tipo': 'esperar'}}


def app_obtener(con_int):
    app = FastAPI()
    if con_int:
        @app.get('/tareas/{tarea_id}')
        async def obtener(tarea_id: int):
            if tarea_id not in TAREAS:
                raise HTTPException(404, 'No existe esa tarea')
            return {'recibido': repr(tarea_id), **TAREAS[tarea_id]}
    else:
        @app.get('/tareas/{tarea_id}')
        async def obtener(tarea_id):          # sin anotacion
            if tarea_id not in TAREAS:
                raise HTTPException(404, f'No existe esa tarea (busque {tarea_id!r})')
            return {'recibido': repr(tarea_id), **TAREAS[tarea_id]}
    return TestClient(app)


def app_prioridad(tipo):
    class Nueva(BaseModel):
        prioridad: tipo

    app = FastAPI()

    @app.post('/tareas')
    async def crear(n: Nueva):
        return {'prioridad': n.prioridad, 'tipo_en_python': type(n.prioridad).__name__}
    return TestClient(app)


def mostrar(cliente, metodo, url, **kw):
    r = cliente.request(metodo, url, **kw)
    cuerpo = r.json()
    if r.status_code == 422:
        cuerpo = [f"{e['loc']}: {e['msg']}" for e in cuerpo['detail']]
    extra = f" json={kw['json']}" if 'json' in kw else ''
    print(f'  {metodo} {url}{extra} -> {r.status_code} {cuerpo}')


if __name__ == '__main__':
    for con_int in (True, False):
        print(f"\n== obtener(tarea_id{': int' if con_int else ''})")
        c = app_obtener(con_int)
        mostrar(c, 'GET', '/tareas/abc')
        mostrar(c, 'GET', '/tareas/1')

    for tipo in (int, str):
        print(f'\n== prioridad: {tipo.__name__}')
        c = app_prioridad(tipo)
        for valor in (3, '3', 'urgente', 2.0, 2.5, True):
            mostrar(c, 'POST', '/tareas', json={'prioridad': valor})
