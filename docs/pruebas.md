# Pruebas de Flucito

Las pruebas sirven para comprobar que los cambios no rompan el flujo que ya funciona. La V1 tiene pruebas automáticas para API, agente, proveedores LLM, documentos, almacén y Google Drive.

## Ejecutar pruebas automáticas

Desde `backend`, con el entorno virtual activo:

`tests/conftest.py` fija credenciales falsas, el modelo y los interruptores de prueba
antes de importar la aplicación. Las pruebas unitarias no dependen de las credenciales
ni del modelo elegidos en el `.env` del desarrollador. Las validaciones reales se
ejecutan por separado y de forma explícita.

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
- Se comprueba que Luna responde sin invocar Groq, que el respaldo pequeño comparte ID y motivo, y que una carga simulada de 11 273 tokens se omite.
- La estimación incluye mensajes de sistema, historial, llamadas/resultados y esquemas de herramientas. Un 413 no se reenvía, ni con respaldo ni sin él.
- Se comprueba que los registros del router omiten contenido y errores privados, y que las etiquetas de actividad no lanzan llamadas auxiliares.

Estas pruebas usan dobles de prueba; no consumen tokens reales de Groq ni OpenAI.

### Responses API y comparación de modelos

`test_responses_api.py` usa el SDK real de OpenAI con transporte HTTP simulado:
verifica el endpoint, esquemas, `call_id`, resultados, streaming dentro de LangGraph,
validación completa del lote, orden de ejecución y detención de escrituras dependientes.
También cubre peticiones mixtas, reducción conservadora de herramientas, compatibilidad
con Groq, adjuntos de salida, coincidencia del cierre SSE con el historial y alcance por fecha.

El protocolo reproducible está en `backend/evaluations/casos_responses.json`.
Desde `backend`, prepara la evaluación sin llamadas pagadas:

```powershell
..\FlucitoEnv\Scripts\python.exe -m evaluations.comparar_responses
```

Con una clave válida y acceso a ambos modelos:

```powershell
..\FlucitoEnv\Scripts\python.exe -m evaluations.comparar_responses --live --repeticiones 3
```

Compara `gpt-5.6-luna` y `gpt-6-luna` con las mismas cinco solicitudes: directa,
factores, carpeta más reporte, restauración y adjunto de reporte. Las herramientas
usan fixtures aislados y nunca modifican Drive real. Registra validación de herramientas,
criterios automáticos del texto final, tareas resueltas, latencia y tokens. Esto no sustituye
la revisión humana ni la prueba de aceptación con la cuenta/Drive reales.

Para medir costo, `--precios ruta.json` recibe un objeto por modelo con
`input_per_million`, `output_per_million` y `cached_input_per_million` opcional, en USD.
Sin tarifas explícitas o sin uso verificable, el costo queda en `null`. No se inventan
precios ni se cambia el modelo predeterminado a partir de fixtures.

El primer intento local quedó en `docs/evaluaciones/responses-cuenta-local.json` con
HTTP 401. Ese bloqueo fue resuelto el 22-11-2026: los resultados reales están en
`docs/evaluaciones/responses-cuenta-validada.json` (ambos modelos, 5/5 casos cada uno)
y `docs/evaluaciones/responses-integracion-real.json` (chat real directo, factores y
consulta conjunta con Drive, dos enlaces accesibles, SSE e historial coincidentes).
Responses se activó solo dentro del proceso de prueba. No se modificó Drive real.
Las tarifas verificadas y los límites de las estimaciones de costo se documentan en
el plan de implementación; el protocolo sin mediciones sigue en `responses-protocolo.json`.

### Documentos y almacén

- `test_almacen_upload.py` verifica agrupación de documentos por factura.
- `test_almacen_pipeline.py` comprueba apoyo TXT, coincidencia de códigos, detección de XML, fechas y eliminación de duplicados.
- Los archivos temporales de prueba no deben mezclarse con `backend/datos/almacen` real.

### Google Drive

- `test_restauracion_carpetas.py` cubre la restauración de contenido en la misma fecha,
  varias fechas, TXT de apoyo frente a TXT generados, reportes generales e individuales,
  idempotencia, permiso denegado, respuesta perdida, reanudación, ambigüedad, archivos
  ajenos y conservación de configuración. Comprueba la respuesta recuperada del chat
  después de restaurar y un error de redacción.
- Si está disponible la copia local del 17 en `C:\Users\rober\Proyectos\Docs`, una prueba
  usa únicamente sus nombres y estructura para poblar Drive simulado. No modifica esa copia:
  reproduce dos carpetas de proveedor, dos XML y seis reportes, sin generales en la raíz.

- `test_operaciones_drive.py` simula respuesta perdida tras escribir, desconexión al verificar,
  acceso denegado, cambio del origen, fallo del diario, carpeta ambigua y elección por ID.
- Verifica que un fallo de redacción conserve el destino confirmado y una sola escritura,
  que el límite de rondas use el diario sin llamar al modelo, y que el registro sobreviva
  a reabrir la base. Comprueba también la propagación real de configuración de la herramienta.
- Estas pruebas usan Drive simulado y una base SQLite temporal; no modifican el Drive real.

- `test_google_drive.py` comprueba agrupación de archivos por subcarpeta.
- `test_drive_state.py` verifica que solo se consideren documentos nuevos.
- Las pruebas no deberían depender de una cuenta real ni modificar el Drive personal.

## Prueba manual local

### Actividad del chat (fase 4)

Desde frontend: `npx playwright install chromium`, `npm run test:e2e` y `npm run build`.
Playwright monta componentes y hook reales en una página de prueba aislada con API simulada.
Comprueba escritorio/móvil, teclado, panel cerrado, modo oscuro, errores, recuperación,
historial antiguo, interrupción de red y recarga: un solo POST y pasos sin duplicados.
Las capturas se guardan en test-results, excluido de Git; esa página de prueba no entra
en el build de producción. El backend cubre eventos reales de restauración, actualización
por ID, parciales y resúmenes consolidados sin contenido cifrado.

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
