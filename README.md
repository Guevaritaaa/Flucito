# Flucito 🤖

Flucito es un agente de Inteligencia Artificial que estoy construyendo para Interflu, una empresa dedicada a refacciones y soluciones hidráulicas y neumáticas.

Esta primera versión busca resolver algo concreto: recibir documentos de facturas, organizarlos, extraer información útil y convertirla en una base operativa para el almacén. A partir de ahí, el proyecto puede crecer hacia facturación automática, consultas sobre inventario y apoyo para tomar mejores decisiones comerciales.

## Desarrolladores

- Roberto Carlos Luis Guevara
- Jatziri Guadalupe Camacho Madero

## Estado actual

La V1 ya cuenta con un flujo funcional de conversación, carga de documentos, almacenamiento en Google Drive y generación de reportes en Excel. El frontend actual es una interfaz de pruebas; la prioridad de esta etapa es consolidar el backend, probarlo y dejar documentado cómo funciona.

## Qué puede hacer actualmente

- Mantener una conversación con contexto por sesión.
- Usar Groq como proveedor principal de lenguaje.
- Cambiar automáticamente a OpenAI cuando el proveedor principal falla.
- Recibir XML, PDF y TXT desde la interfaz.
- Agrupar documentos relacionados con una misma factura.
- Subir y organizar documentos en Google Drive.
- Extraer datos estructurados de comprobantes fiscales XML.
- Usar PDF o TXT como apoyo cuando están disponibles.
- Actualizar una base acumulativa de entradas de almacén.
- Generar y descargar un archivo Excel compatible con el flujo de trabajo de Aspel SAE.

## Stack tecnológico

- **Backend:** Python, FastAPI y LangGraph.
- **Modelos de lenguaje:** Groq como proveedor principal y OpenAI como fallback.
- **Documentos y Excel:** XML, PDF, TXT, pandas y openpyxl.
- **Almacenamiento:** Google Drive API.
- **Frontend V1:** HTML, CSS y JavaScript.
- **Despliegue:** Render.
- **Monitoreo:** endpoint `/health` y cron job externo.

## Estructura del proyecto

```text
Flucito/
├── backend/
│   ├── app/
│   │   ├── agents/             # Grafo, estado, prompt, herramientas y fallback
│   │   ├── api/v1/routes/      # Endpoints de chat y almacén
│   │   ├── core/               # Configuración y variables de entorno
│   │   ├── schemas/            # Modelos de entrada y respuesta
│   │   └── services/almacen/   # Extracción, Excel y Google Drive
│   ├── tests/                  # Pruebas automatizadas
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── index.html
    ├── script.js
    └── style.css
```

## Ejecutar localmente

Desde `backend`:

```powershell
python -m venv Flucitoenv
.\Flucitoenv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Después hay que completar `.env` con las claves y configuraciones correspondientes. Ese archivo no debe subirse a Git.

Para iniciar la API:

```powershell
fastapi dev app/main.py
```

La API queda disponible en `http://127.0.0.1:8000` y su documentación interactiva en `http://127.0.0.1:8000/docs`.

`fastapi dev` es el comando de desarrollo de FastAPI: activa recarga automática y escucha en localhost. Uvicorn sigue siendo válido; el CLI de FastAPI lo utiliza internamente. Para producción se usa `fastapi run app/main.py` o el comando de Uvicorn configurado en Render.

## Variables de entorno

La plantilla completa está en [`backend/.env.example`](backend/.env.example). Las variables principales son:

La explicación de configuración local, Render, OAuth y cuenta de servicio está en [`docs/variables-entorno.md`](docs/variables-entorno.md).

La guía de uso diario está en [`docs/flujo-usuario.md`](docs/flujo-usuario.md).

- `GROQ_API_KEY` y `GROQ_MODEL`: proveedor y modelo principales.
- `OPENAI_API_KEY` y `OPENAI_MODEL`: proveedor y modelo de respaldo.
- `LLM_PRIMARY_PROVIDER`: normalmente `groq`.
- `LLM_FALLBACK_ENABLED`: activa o desactiva el fallback.
- `GOOGLE_DRIVE_FOLDER_ID`: carpeta raíz de documentos.
- `GOOGLE_OAUTH_CLIENT_JSON` y `GOOGLE_OAUTH_TOKEN_JSON`: configuración OAuth para Render.
- `ALMACEN_CARPETA_DATOS`: ubicación local de archivos generados.

## Cómo funciona el agente

El endpoint `POST /api/v1/chat` envía cada mensaje al grafo de LangGraph. Flucito puede responder directamente o decidir que necesita consultar la herramienta de entradas de almacén.

```text
mensaje → modelo → herramienta → modelo → respuesta
```

El fallback se activa cuando el proveedor principal devuelve errores recuperables, como modelo no disponible, límite de peticiones o errores temporales.

La herramienta disponible y su funcionamiento están descritos en [`docs/herramientas.md`](docs/herramientas.md).

La memoria actual usa `MemorySaver` y `session_id`. Funciona para la V1, pero vive en la memoria del proceso: si Render reinicia el servicio, las conversaciones se pierden. Una versión posterior deberá guardar sesiones en una base de datos.

## Flujo de documentos y almacén

1. El usuario selecciona XML, PDF o TXT desde el frontend.
2. `POST /api/v1/almacen/upload` recibe y agrupa los archivos por factura.
3. Los documentos se suben y organizan en Google Drive.
4. La herramienta del agente sincroniza documentos nuevos.
5. El extractor obtiene datos fiscales y conceptos del XML.
6. PDF o TXT sirven como apoyo cuando hace falta validar o completar información.
7. Se actualiza el Excel acumulativo de entradas de almacén.
8. Flucito devuelve un resumen y habilita la descarga del archivo.

## Endpoints principales

- `GET /health`: comprobación ligera del servicio.
- `POST /api/v1/chat`: conversación con Flucito.
- `POST /api/v1/almacen/upload`: carga documentos a Google Drive.
- `GET /api/v1/almacen/download`: descarga la base acumulativa de almacén.

## Pruebas

Desde `backend`:

```powershell
python -m pytest tests -q --basetemp ..\pytest-temp
```

Las pruebas cubren salud de la API, chat, fallback de proveedores, carga de archivos, estado de Drive y procesamiento del almacén.

La guía completa de pruebas automáticas y manuales está en [`docs/pruebas.md`](docs/pruebas.md).

## Despliegue

El backend está desplegado en Render. Las variables de entorno se configuran directamente en el panel del servicio y no forman parte del repositorio.

Para evitar que la instancia gratuita permanezca inactiva durante la jornada, un cron job externo consulta periódicamente `/health`. Ese endpoint no ejecuta modelos ni herramientas; solamente confirma que la API está activa.

## Hoja de ruta

### V1: consolidación

- Mantener estable el flujo actual.
- Mejorar manejo de errores.
- Aumentar cobertura de pruebas.
- Documentar configuración y decisiones técnicas.

### V2: evolución del asistente

- Sustituir la interfaz de pruebas por el diseño completo de Figma.
- Guardar conversaciones en una base de datos.
- Consultar información comercial y de inventario desde los sistemas de Interflu.
- Generar reportes de ventas, existencias y productos con baja rotación.
- Preparar automatización de facturas y tareas repetitivas del almacén.

## Nota de alcance

Flucito todavía es una primera versión funcional, no un sistema terminado de producción. La automatización de facturas, las recomendaciones de inventario y el modelo de machine learning forman parte de la evolución prevista, pero requieren más datos, validaciones y pruebas antes de automatizar decisiones importantes.
