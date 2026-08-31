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
- `tools.py` expone funciones de negocio como herramientas para el modelo.
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
fin       ToolNode
               ↓
          modelo LLM
               ↓
             fin
```

Si Groq falla por un error recuperable, `llm_router.py` permite intentar la misma operación con OpenAI. La herramienta se enlaza a ambos modelos para que el fallback pueda continuar el ciclo de tools.

### `app/services/almacen`

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
