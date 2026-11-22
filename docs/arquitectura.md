# Arquitectura de Flucito

Este documento explica cómo está conectada la primera versión de Flucito. La idea es que, al volver al proyecto después de varios días, sea fácil seguir el recorrido de una petición sin tener que leer todo el código.

## Vista general

```text
Frontend
   │
   ├── POST /api/v1/chat
   └── POST /api/v1/almacen/upload
              │
              ▼
          FastAPI
              │
              ▼
      Grafo de LangGraph
              │
       ┌──────┴──────┐
       │             │
  Respuesta      ToolNode
       │             │
       │       herramienta de
       │       entradas de almacén
       │             │
       │       sincronización
       │       Google Drive
       │             │
       │       extracción XML
       │       y apoyo PDF/TXT
       │             │
       └──────► Excel acumulativo
```

## Capas del backend

### `app/api`

Contiene los endpoints HTTP:

- `routes/chat.py` recibe mensajes y devuelve respuestas del agente.
- `routes/almacen.py` recibe documentos, los sube a Drive y permite descargar el Excel.

Los endpoints validan la entrada y traducen errores internos a respuestas HTTP. La lógica de negocio vive en `services`, no en las rutas.

### `app/agents`

Aquí vive el comportamiento del asistente:

- `state.py` define el estado de conversación.
- `prompts.py` contiene las instrucciones del agente.
- `llm_router.py` crea los modelos y configura proveedor principal y fallback.
- `tools/` expone funciones de negocio como herramientas para el modelo.
- `seleccion_tools.py` limita las herramientas solo para consultas inequívocas de factores.
- `ejecucion_tools.py` valida el lote completo y ejecuta sus llamadas en orden.
- `graph.py` conecta modelo, herramientas y memoria mediante LangGraph.

El flujo normal es:

```text
mensaje del usuario
        ↓
modelo LLM
        ↓
¿solicita una herramienta?
   ┌────┴────┐
  no         sí
  ↓          ↓ 
fin       Validación y ejecución secuencial
               ↓
          modelo LLM
               ↓
             fin
```

OpenAI (Luna 6) es el proveedor principal. Ante un error recuperable, `llm_router.py` permite usar Groq únicamente si los mensajes, esquemas de herramientas y reserva de salida caben en `GROQ_TPM_BUDGET` (8000 por defecto). Un HTTP 413 no se reenvía. Cada intento registra proveedor, modelo, duración, resultado y motivo con un ID compartido, sin contenido ni credenciales. Las etiquetas de actividad son locales y no invocan modelos. Las herramientas se enlazan a ambos proveedores.

`OPENAI_USE_RESPONSES_API` elige Responses API o Chat Completions. La integración
usa el SDK real a través de ChatOpenAI, conserva bloques e identificadores Responses
en la memoria y entrega cada resultado como `ToolMessage.tool_call_id`; LangChain
lo convierte a `function_call_output.call_id`. Para Groq o Chat Completions se envía
una copia normalizada de los mensajes del modelo, sin bloques propios de Responses
ni resúmenes de razonamiento. El historial original no se modifica.

Las llamadas del lote se validan con Pydantic (tipos estrictos, campos extra prohibidos,
función conocida e IDs únicos), antes de ejecutar la primera. Las respuestas siguen
el orden de las llamadas. Si una falla, se cancela o requiere confirmación, las siguientes
no se ejecutan. El ID de cada llamada también acompaña las respuestas de error.
Se desactiva `parallel_tool_calls` para OpenAI; la ejecución local ordenada se aplica
a ambos proveedores. La generación de reportes admite `carpeta_especifica` por fecha
o ID, rechaza ambigüedad antes de descargar/procesar y conserva la selección durante
las confirmaciones.

El evento SSE final, el texto provisional al completar el job y el historial usan
el mismo `ChatResponse`, incluidos los enlaces a reportes. Los bloques de razonamiento
y argumentos no forman parte del texto de respuesta. En esta fase, los adjuntos son
los enlaces a reportes del flujo existente; la carga XML/PDF/TXT sigue pasando por
`/almacen/upload`. No se añadieron adjuntos binarios a `ChatRequest`.

### `app/services/almacen`

Los movimientos de Drive pasan por `operaciones_drive.py`. El diario en la base SQL
guarda el intento antes del `update` y lo confirma con un `get` independiente.
Las escrituras no tienen reintentos automáticos. Si se pierde la conexión, se consulta
la ubicación por ID; una operación incierta queda pendiente y bloquea nuevos movimientos
del mismo elemento mientras no pueda verificarse su destino. Los estados son
`confirmada`, `fallida` y `pendiente_verificar`; la respuesta agregada distingue resultados parciales.

Cada ejecución del chat propaga `drive_request_id` mediante la configuración de
LangGraph hasta las herramientas. Si falla la redacción o se alcanza el límite de rondas,
el chat construye la respuesta con el diario y conserva ese texto en el historial.
Los movimientos puntuales buscan todas las coincidencias dentro de la raíz autorizada;
ante ambigüedad devuelven rutas e IDs para que el usuario elija con `id:...`.
No crean destinos ni fusionan carpetas homónimas automáticamente.

`restablecer_carpeta` devuelve una o varias fechas a su estado sin procesar dentro de
**DOCUMENTOS ENTRADA/AÑO/MES/FECHA**. Resuelve toda la selección y construye un plan
antes de escribir. Primero mueve y verifica los originales XML/PDF/TXT a la raíz de cada fecha;
después envía a papelera los reportes reconocidos `ENTRADAS_ALMACEN_*.xlsx` y
`ENTRADAS_ALMACEN_*_COMAS.txt`/`_TABS.txt`, y finalmente las subcarpetas verificadas vacías.
El plan y el resultado agregado también se guardan en el diario. La verificación final exige
el mismo ID y padre de la fecha y exactamente los originales previstos. Solo entonces libera
sus IDs del estado incremental local, sin borrar factores o configuración. El resultado puede
ser `confirmada` o `parcial`; nunca convierte un fallo de verificación en éxito.

La restauración global de pruebas delega este mismo flujo a todas las fechas, sin crear la
bandeja antigua. La nueva ruta de papelera verifica el resultado y no reintenta escrituras
inciertas. Las operaciones genéricas ajenas a esta restauración conservan sus propios flujos.

La auditoría ya no considera mal ubicada una fecha sin reporte. La reubicación antigua
hacia ENTRADAS AL INVENTARIO queda inactiva; ordenar conserva la jerarquía actual,
incluidas sus fechas vacías. Crear una fecha por nombre corto usa DOCUMENTOS ENTRADA/AÑO/MES.
Se conserva lectura de cargas antiguas y migración explícita de cargas procesadas hacia la
jerarquía vigente, además de las rutas que el usuario indique expresamente.

El diario crea su tabla `operaciones_drive` si no existe y requiere permiso de creación
en la base. Debe conservarse PostgreSQL o el volumen SQLite entre reinicios. La exclusión
de movimientos simultáneos es por proceso; esta versión debe ejecutarse con un solo
worker de backend para mantener esa garantía. La recuperación nunca reenvía escrituras inciertas.

Contiene la lógica específica de documentos y almacén:

- `extractor.py` lee datos fiscales y conceptos desde XML CFDI.
- `apoyo.py` busca información complementaria en PDF o TXT.
- `excel.py` crea y actualiza el libro acumulativo.
- `resumen.py` genera el resumen que utiliza el agente.
- `fuentes/google_drive_client.py` crea el cliente autenticado de Drive.
- `fuentes/subidor.py` agrupa y sube documentos.
- `fuentes/sincronizador.py` detecta y descarga documentos nuevos.
- `fuentes/estado_drive.py` evita procesar repetidamente las mismas carpetas.

## Flujo de carga de documentos

La carga y el procesamiento son dos pasos relacionados, pero separados:

1. El frontend envía XML, PDF o TXT a `POST /api/v1/almacen/upload`.
2. FastAPI guarda temporalmente los archivos recibidos.
3. `subidor.py` identifica documentos de una misma factura.
4. Los archivos se organizan en Google Drive.
5. El directorio temporal se elimina al terminar la solicitud.
6. Cuando el usuario pide un reporte, el agente invoca `generar_entradas_almacen`.
7. `sincronizador.py` lista carpetas nuevas de Drive y descarga sus archivos.
8. `extractor.py` obtiene datos del XML.
9. `apoyo.py` usa PDF o TXT cuando se necesita información complementaria.
10. `excel.py` actualiza el libro acumulativo.
11. El agente devuelve un resumen y el frontend ofrece descargarlo.

## Autenticación de Google Drive

La aplicación soporta dos formas de autenticación:

- OAuth: opción usada para trabajar con el Drive personal y recomendada en Render.
- Cuenta de servicio: alternativa para carpetas compartidas y pruebas.

La configuración se carga desde variables de entorno. Los JSON de credenciales y tokens son archivos locales o valores privados de Render; no forman parte del repositorio.

## Memoria de conversación

El grafo usa `MemorySaver` con `session_id` como identificador de hilo. Mientras el proceso siga activo, los mensajes de una sesión se conservan y el agente puede usar el contexto anterior.

Esta memoria no es persistente. Un reinicio o nuevo despliegue de Render la elimina. Para conservar conversaciones en una siguiente versión habrá que reemplazarla por un checkpointer respaldado por una base de datos.

## Archivos generados

Los datos de trabajo se guardan en `backend/datos/almacen` por defecto:

- Excel acumulativo de entradas.
- Resúmenes JSON.
- Estado de carpetas procesadas.
- Documentos temporales descargados durante la sincronización.

Estos archivos pertenecen al entorno de ejecución y están excluidos de Git. Si se necesita un caso de prueba reproducible, debe agregarse una copia pequeña y anonimizada dentro de `backend/tests`.

## Límites actuales

- La memoria se pierde al reiniciar el backend.
- El procesamiento de almacén ocurre dentro de la solicitud; archivos grandes pueden tardar.
- La base operativa actual es un Excel, no una base de datos multiusuario.
- Google Drive depende de credenciales, permisos y disponibilidad externa.
- El fallback cambia de proveedor, pero no guarda automáticamente un historial compartido entre procesos.

Estos límites son conocidos de la V1 y sirven como guía para las siguientes mejoras.
