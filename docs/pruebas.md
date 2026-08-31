# Pruebas de Flucito

Las pruebas sirven para comprobar que los cambios no rompan el flujo que ya funciona. La V1 tiene pruebas automáticas para API, agente, proveedores LLM, documentos, almacén y Google Drive.

## Ejecutar pruebas automáticas

Desde `backend`, con el entorno virtual activo:

```powershell
python -m pytest tests -q --basetemp ..\pytest-temp
```

El argumento `--basetemp` coloca los archivos temporales fuera de `backend`. En Windows puede evitar errores de permisos sobre `backend/.pytest_cache` o carpetas temporales creadas por ejecuciones anteriores.

Para ejecutar una categoría concreta:

```powershell
python -m pytest tests/test_llm_router.py -q --basetemp ..\pytest-temp
python -m pytest tests/test_almacen_pipeline.py -q --basetemp ..\pytest-temp
python -m pytest tests/test_health.py -q --basetemp ..\pytest-temp
```

Para ver más detalle:

```powershell
python -m pytest tests -vv --basetemp ..\pytest-temp
```

## Qué cubren las pruebas actuales

### API y chat

- `test_health.py` confirma que `/health` responde y no ejecuta procesos pesados.
- `test_chat_content.py` verifica que las respuestas del modelo se conviertan correctamente a texto.

### Proveedores LLM

- `test_llm_router.py` comprueba el fallback ante errores recuperables.
- También confirma que errores no reintentables no se oculten.
- Se valida el reconocimiento de modelos no disponibles.

Estas pruebas usan dobles de prueba; no consumen tokens reales de Groq ni OpenAI.

### Documentos y almacén

- `test_almacen_upload.py` verifica agrupación de documentos por factura.
- `test_almacen_pipeline.py` comprueba apoyo TXT, coincidencia de códigos, detección de XML, fechas y eliminación de duplicados.
- Los archivos temporales de prueba no deben mezclarse con `backend/datos/almacen` real.

### Google Drive

- `test_google_drive.py` comprueba agrupación de archivos por subcarpeta.
- `test_drive_state.py` verifica que solo se consideren documentos nuevos.
- Las pruebas no deberían depender de una cuenta real ni modificar el Drive personal.

## Prueba manual local

Inicia el backend desde `backend`:

```powershell
fastapi dev app/main.py
```

`fastapi dev` inicia el servidor en modo desarrollo y recarga los cambios automáticamente. Para ejecutar la aplicación sin recarga, puedes usar `fastapi run app/main.py` o Uvicorn con el comando configurado para producción.

Comprueba salud de la API:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Resultado esperado:

```text
status
------
ok
```

Después abre `http://127.0.0.1:8000/docs` y revisa los endpoints disponibles. Para probar el chat desde Swagger, envía un cuerpo similar a:

```json
{
  "mensaje": "Hola, ¿qué puedes hacer?",
  "session_id": "prueba-local"
}
```

Para probar documentos, utiliza el frontend o carga un conjunto pequeño de XML/PDF/TXT de prueba. Confirma que:

1. Los archivos sean aceptados.
2. Se agrupen correctamente.
3. La respuesta indique resultado de la carga.
4. El reporte se genere solo después de solicitarlo en el chat.
5. El Excel se pueda descargar.

## Prueba manual en Render

Después de hacer push y esperar el despliegue:

1. Abre `https://tu-dominio.onrender.com/health`.
2. Confirma respuesta HTTP `200`.
3. Envía un mensaje sencillo desde el frontend.
4. Comprueba que el chat responda.
5. Fuerza una prueba de fallback con un modelo inválido solo en un entorno controlado.
6. Restaura el modelo correcto después de la prueba.
7. Sube un lote pequeño de documentos.
8. Solicita el reporte.
9. Descarga el Excel.
10. Revisa los logs de Render.

No uses archivos fiscales reales para pruebas repetidas si no quieres duplicarlos en Drive. Usa un lote pequeño y verifica la hoja de errores.

## Criterio de aprobación de la V1

La versión se considera estable cuando:

- todas las pruebas automáticas pasan;
- `/health` responde `200`;
- el chat responde con el proveedor principal;
- el fallback responde cuando el proveedor principal falla;
- los documentos llegan a Drive;
- el reporte procesa archivos nuevos sin duplicarlos;
- el Excel se descarga correctamente;
- los errores aparecen en la hoja correspondiente y en los logs.

## Si una prueba falla

Lee primero el error completo y clasifícalo:

- **Permiso de Windows:** cambia `--basetemp` a una carpeta temporal fuera de `backend`.
- **Dependencia faltante:** activa `Flucitoenv` y ejecuta `pip install -r requirements.txt`.
- **Variable de entorno faltante:** revisa `backend/.env`.
- **Error de Drive:** revisa credenciales, carpeta raíz, permisos y cuota.
- **Error del modelo:** revisa el nombre configurado y las claves del proveedor.

No desactives una prueba solo para obtener una ejecución verde. Primero determina qué comportamiento está protegiendo.
