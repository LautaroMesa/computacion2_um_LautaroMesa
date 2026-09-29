# Clase 6 — Señales

Ejercicio obligatorio 5: servidor que responde a señales.

## Qué hace

`servidor_signals.py` simula un servidor que procesa una request cada 0.1 s y
registra un manejador por señal:

| Señal | Acción |
|---|---|
| `SIGTERM` / `SIGINT` | Baja la bandera `ejecutando`; el loop termina y corre `cleanup()` (cierra el log) |
| `SIGHUP` | Relee `config.json` (si está roto, se queda con la config anterior) |
| `SIGUSR1` | Muestra uptime, requests, errores, recargas, rotaciones y config |
| `SIGUSR2` | Rota el log: `server.log` → `server.log.<timestamp>` y abre uno nuevo |

Al arrancar muestra el PID y los comandos `kill` para mandarle cada señal.

### Decisión de diseño: los handlers hacen lo mínimo

Un handler puede ejecutarse **entre cualquier par de instrucciones** del programa
principal. Por eso el shutdown y la rotación no se hacen dentro del handler:

- `SIGTERM` solo pone `ejecutando = False`. El cleanup lo hace el loop al salir,
  en un punto conocido.
- `SIGUSR2` solo pone `rotar_pendiente = True`. Si el handler cerrara el archivo
  directamente, podría hacerlo justo después de que `procesar_request()` agarró
  `self.log` y antes del `.write()`, y el write fallaría sobre un archivo cerrado.
  La rotación la hace el loop al principio de la vuelta siguiente.

`SIGHUP` y `SIGUSR1` sí trabajan en el handler, porque solo leen o reemplazan
un diccionario de una vez y no hay un estado intermedio que se pueda romper.

## Cómo correr

Hacen falta dos terminales: una para el servidor y otra para mandarle señales.

```bash
docker build -t clase6 .
docker run --rm -it --name senales clase6 python servidor_signals.py
```

En otra terminal (dentro del contenedor el servidor corre como PID 1):

```bash
docker exec senales kill -USR1 1     # stats
docker exec senales kill -HUP 1      # recargar config
docker exec senales kill -USR2 1     # rotar logs
docker exec senales ls               # aparece server.log.<timestamp>
docker exec senales kill 1           # shutdown limpio
```

> Como es PID 1, el kernel **no** le aplica la acción por defecto a las señales
> que no tienen handler. Acá no importa porque todas las que usamos tienen uno,
> pero es la razón por la que en Docker se usa `--init` o `tini`.

## Salida de una corrida (verificada en Linux)

```
Servidor iniciado (PID 758)
Comandos disponibles:
  kill -HUP 758   -> Recargar config
  kill -USR1 758  -> Ver stats
  kill -USR2 758  -> Rotar logs
  kill 758        -> Shutdown

[SIGUSR1] === Estadisticas ===
  Uptime: 1.0s
  Requests: 10
  ...
[SIGHUP] Recargando configuracion...
[SIGHUP] Nueva config: {'max_conexiones': 200, 'timeout': 5, 'recargado': '...'}

[SIGUSR2] Rotacion pedida
[SIGUSR2] Logs rotados a server.log.1790684618

[SIGTERM] Iniciando shutdown...
Realizando cleanup...
Servidor terminado. Requests procesadas: 30
```

## Checklist de la consigna

- [x] SIGTERM/SIGINT → shutdown limpio
- [x] SIGHUP → recarga configuración (lee `config.json` de verdad)
- [x] SIGUSR1 → estadísticas
- [x] SIGUSR2 → rotación de logs (renombra el archivo de verdad)
- [x] Muestra PID y comandos al inicio
- [x] Cleanup antes de terminar
