# Flucito

Flucito es el asistente virtual que estoy construyendo para Interflu, una refaccionaria industrial y neumática.

La primera versión ya puede conversar, recibir documentos de facturas, guardarlos en Google Drive y generar una base acumulativa de entradas de almacén en Excel. El objetivo no es solamente tener un chat: quiero convertirlo poco a poco en un agente que ayude con la facturación, almacén y decisiones de inventario.

## Qué puede hacer actualmente

- Mantener una conversación por sesión.
- Usar Groq como proveedor principal de lenguaje.
- Cambiar a OpenAI cuando Groq falla o no está disponible.
- Recibir archivos XML, PDF y TXT desde el frontend.
- Agrupar documentos relacionados con una factura.
- Subir documentos a una carpeta de Google Drive.
- Leer documentos de Drive y actualizar la base acumulativa del almacén.
- Generar y descargar un archivo Excel.
- Trabajar con XML como fuente principal, PDF como apoyo y TXT cuando no existe PDF.

## Estructura general

```text
Flucito/
├── backend/
│   ├── app/
│   │   ├── agents/             # Grafo, estado, prompt, herramientas y fallback
│   │   ├── api/v1/routes/      # Endpoints de chat y almacén
│   │   ├── core/               # Configuración desde variables de entorno
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

## Cómo ejecutarlo localmente

Desde `backend`:

```powershell
python -m venv Flucitoenv
.\Flucitoenv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Después, completa `.env` con las claves y configuraciones necesarias. Nunca subas ese archivo a Git.

Para iniciar la API:

```powershell
uvicorn app.main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000`. La documentación interactiva de FastAPI está en `/docs`.

## Variables de entorno

La plantilla está en [`backend/.env.example`](backend/.env.example). Las variables principales son:

- `GROQ_API_KEY`: clave del proveedor principal.
- `GROQ_MODEL`: modelo usado por Groq.
- `OPENAI_API_KEY`: clave del proveedor de respaldo.
- `OPENAI_MODEL`: modelo usado por OpenAI.
- `LLM_PRIMARY_PROVIDER`: normalmente `groq`.
- `LLM_FALLBACK_ENABLED`: activa o desactiva el respaldo.
- `GOOGLE_DRIVE_FOLDER_ID`: id de la carpeta de drive usada.
- `GOOGLE_OAUTH_CLIENT_JSON` y `GOOGLE_OAUTH_TOKEN_JSON`: configuración OAuth para Render.
- `ALMACEN_CARPETA_DATOS`: ubicación local de archivos generados; si se omite, usa `backend/datos/almacen`.

## Cómo funciona el chat

El endpoint `POST /api/v1/chat` envía el mensaje al grafo de LangGraph. El modelo puede responder directamente o solicitar la herramienta de entradas de almacén.

Cuando solicita la herramienta, el flujo es:

```text
mensaje → modelo → herramienta de almacén → modelo → respuesta
```

El grafo conserva la conversación mediante `MemorySaver` y `session_id`. Esta memoria es temporal: se pierde si Render reinicia el proceso. Para una versión posterior será necesario guardar las conversaciones en una base de datos.

## Flujo de documentos y almacén

1. El frontend recibe XML, PDF o TXT.
2. `POST /api/v1/almacen/upload` agrupa los archivos por factura.
3. Los documentos se suben a Google Drive.
4. La herramienta del agente sincroniza documentos nuevos.
5. El extractor obtiene datos del XML y usa PDF/TXT como apoyo.
6. Se actualiza la base acumulativa.
7. El agente responde con un resumen y ofrece descargar el Excel.

Endpoints principales:

- `GET /health`: comprobación ligera del servicio.
- `POST /api/v1/chat`: conversación con Flucito.
- `POST /api/v1/almacen/upload`: carga documentos a Google Drive.
- `GET /api/v1/almacen/download`: descarga la base de almacén.

## Pruebas

Desde `backend`:

```powershell
python -m pytest tests -q --basetemp ..\pytest-temp
```

Las pruebas cubren salud de la API, chat, fallback de proveedores, carga de documentos, estado de Drive y procesamiento del almacén.

## Despliegue

El backend se despliega en Render. Las variables de `.env` deben configurarse en el panel de Render; no se guardan en el repositorio.

Después de cada cambio importante:

1. Ejecutar las pruebas localmente.
2. Probar la ruta afectada en Render.
3. Revisar los logs.
4. Crear un commit que explique el cambio.

## Estado de esta versión

Esta es la primera versión funcional. Ya existe el flujo principal, pero todavía quedan tareas importantes: persistir conversaciones, mejorar manejo de errores de Google Drive, agregar más pruebas de integración y documentar decisiones técnicas conforme el proyecto crezca.
