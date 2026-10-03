# Herramientas del agente

Una herramienta, o *tool*, es una función que el modelo puede solicitar cuando necesita realizar una acción concreta del sistema. En Flucito, cada tool representa un proceso específico de Interflu que fue automatizado para reducir tiempos, evitar trabajo repetitivo, disminuir errores y aprovechar mejor la información disponible.

El agente dispone de `generar_entradas_almacen` y `buscar_reporte_historico`. Cada herramienta tiene un propósito delimitado: una actualiza el reporte actual y la otra localiza reportes anteriores guardados en Drive.

## `generar_entradas_almacen`

### Para qué sirve

Sincroniza documentos de facturas, extrae información y genera o actualiza el Excel acumulativo de entradas de almacén.

### Cuándo se usa

El modelo debe invocarla cuando el usuario pide algo relacionado con:

- entradas de almacén;
- compras acumuladas;
- movimientos de productos;
- actualización de la base;
- generación del reporte de almacén;
- procesamiento de facturas nuevas.

Para una pregunta normal o una explicación general, el modelo responde sin usar la herramienta.

### Entrada

Actualmente no recibe argumentos:

```text
generar_entradas_almacen()
```

La herramienta obtiene su configuración desde las variables de entorno y decide si trabaja con Google Drive o con la carpeta local.

### Selección del origen

Usa Google Drive cuando existen:

- `GOOGLE_DRIVE_FOLDER_ID`; y
- al menos una credencial OAuth o de cuenta de servicio.

Si no existe una configuración completa de Drive, utiliza `ALMACEN_CARPETA_DATOS` o la ruta local predeterminada `backend/datos/almacen`.

### Flujo con Google Drive

1. Se conecta a Google Drive con OAuth o cuenta de servicio.
2. Lista las carpetas de carga por fecha dentro de `ENTRADAS AL INVENTARIO`.
3. Busca documentos XML, PDF y TXT.
4. Consulta el estado de sincronización.
5. Descarga únicamente carpetas nuevas o pendientes.
6. Procesa los documentos descargados.
7. Actualiza el Excel y el resumen.
8. Archiva facturas y Excel individuales en `DOCUMENTOS ENTRADA/{fecha}/{proveedor} - {fecha}` y el Excel de la carga en `DOCUMENTOS ENTRADA/{fecha}`.
9. Guarda el estado para evitar duplicados en ejecuciones posteriores.

### Flujo local

Si Drive no está configurado:

1. Revisa que exista la carpeta local.
2. Busca XML disponibles.
3. Procesa la carpeta.
4. Genera o actualiza el Excel acumulativo.
5. Lee el resumen generado.

## Resultado de la herramienta

La función devuelve un JSON interno. Ejemplo de operación exitosa:

```json
{
  "ok": true,
  "reporte_generado": true,
  "resumen": {
    "productos_nuevos": 28,
    "documentos_nuevos": 6
  }
}
```

El chat no muestra rutas internas ni credenciales. Usa el resumen para redactar una respuesta y ofrece el endpoint de descarga del Excel.

Casos importantes:

- `reporte_generado: true`: se procesaron documentos y se actualizó el reporte.
- `reporte_generado: false`: la conexión funciona, pero no hay documentos nuevos.
- `ok: false`: ocurrió un problema y el reporte no debe considerarse actualizado.

## Efectos secundarios

La herramienta sí modifica información del entorno:

- descarga documentos de Drive;
- actualiza el estado de sincronización;
- crea o reemplaza el Excel acumulativo;
- escribe el resumen JSON;
- registra errores del procesamiento.

Por eso no debe invocarse para preguntas que no pidan consultar o actualizar el almacén.

## `buscar_reporte_historico`

### Para qué sirve

Busca reportes Excel individuales de almacén en `docs/DOCUMENTOS ENTRADA/{fecha}` y sus subcarpetas. La fecha es la que aparece en el nombre de la carpeta de carga archivada.

### Cuándo se usa

Se invoca cuando el usuario pide un reporte anterior por fecha. Si no indica fecha, el agente debe preguntarla. Para actualizar el reporte actual se usa `generar_entradas_almacen` y no se solicita fecha.

### Entrada y resultado

Acepta una fecha `DD-MM-AAAA`, `DD/MM/AAAA` o `AAAA-MM-DD`. Devuelve los nombres de reportes encontrados y el chat agrega un botón para descargar cada Excel. La descarga vuelve a validar que el archivo pertenezca a la carpeta de Drive configurada y a la fecha solicitada.

Si no hay coincidencias, la herramienta devuelve una lista vacía y el agente informa que no encontró reportes para esa fecha.

## Qué no hace todavía

- No crea facturas fiscales.
- No modifica directamente Aspel SAE.
- No cambia existencias en un ERP.
- No recomienda compras automáticamente.
- No recibe rutas de archivos desde el modelo.
- No permite al modelo inventar qué documentos procesar.

La herramienta procesa documentos encontrados en el origen configurado. Esta separación evita que el LLM controle rutas locales o acceda directamente a archivos privados.

## Herramientas que no pertenecen al agente

`POST /api/v1/almacen/upload` es un endpoint de FastAPI, no una herramienta del modelo. Su función es recibir archivos desde el frontend y subirlos a Google Drive.

`GET /api/v1/almacen/download` tampoco es una herramienta del modelo. Es el endpoint que entrega al usuario el Excel generado.

Esta distinción es importante:

```text
Frontend → endpoint upload → Google Drive
Chat → agente → herramienta de almacén → Excel
Frontend ← endpoint download ← Excel
```

## Agregar una herramienta nueva

Para agregar una acción al agente se debe:

1. Crear una función segura en `backend/app/agents/tools.py`.
2. Decorarla con `@tool`.
3. Agregarla a `HERRAMIENTAS` en `backend/app/agents/graph.py`.
4. Describir en `prompts.py` cuándo debe utilizarse.
5. Validar argumentos y limitar sus efectos.
6. Agregar pruebas automatizadas.
7. Probar primero localmente y después en Render.
