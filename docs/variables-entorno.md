# Configuración del entorno

Flucito toma su configuración desde variables de entorno. En local se guardan en `backend/.env`; en Render se registran desde el panel del servicio.

## Configuración local

Desde `backend`:

```powershell
Copy-Item .env.example .env
```

Después completa `.env` con valores reales. El archivo está excluido de Git y no debe compartirse.

## Variables de modelos

```env
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
LLM_PRIMARY_PROVIDER=groq
LLM_FALLBACK_ENABLED=true
```

`LLM_PRIMARY_PROVIDER` puede ser `groq` u `openai`. Con `LLM_FALLBACK_ENABLED=true`, Flucito intenta el otro proveedor cuando detecta un error recuperable del principal.

El fallback no significa que ambos modelos respondan siempre. Si las dos claves faltan, son inválidas o los modelos no están disponibles, la petición falla.

## Variables de Google Drive

```env
GOOGLE_DRIVE_FOLDER_ID=...
GOOGLE_OAUTH_CLIENT_JSON=...
GOOGLE_OAUTH_TOKEN_JSON=...
```

`GOOGLE_DRIVE_FOLDER_ID` es el identificador de la carpeta raíz que Flucito utiliza para organizar documentos.

Para Render se recomienda OAuth mediante JSON en variables de entorno:

- `GOOGLE_OAUTH_CLIENT_JSON`: contenido completo del cliente OAuth.
- `GOOGLE_OAUTH_TOKEN_JSON`: contenido completo del token autorizado.

El JSON puede ocupar una sola línea. No agregues comillas adicionales alrededor del valor desde el panel de Render, salvo que el formato de la plataforma las requiera.

## OAuth local mediante archivos

En local también puede usarse:

```env
GOOGLE_OAUTH_CLIENT_FILE=ruta/al/cliente_oauth.json
GOOGLE_OAUTH_TOKEN_FILE=token_drive.json
```

El token se guarda localmente después de autorizar la aplicación. Estos archivos deben permanecer fuera del repositorio.

## Cuenta de servicio

Existe una alternativa para carpetas compartidas:

```env
GOOGLE_SERVICE_ACCOUNT_JSON=...
GOOGLE_SERVICE_ACCOUNT_FILE=ruta/al/service-account.json
```

La cuenta de servicio debe tener acceso a la carpeta de Drive. Para subir archivos al Drive personal, OAuth suele ser más conveniente porque la operación utiliza el almacenamiento de la cuenta del usuario.

No mezcles OAuth y cuenta de servicio sin una razón concreta. El cliente prioriza OAuth cuando existe configuración OAuth válida.

## Carpeta de datos

```env
ALMACEN_CARPETA_DATOS=
```

Si se deja vacía, el backend usa `backend/datos/almacen`. Ahí se guardan el Excel acumulativo, resúmenes, estado de sincronización y archivos de trabajo.

En Render ese almacenamiento es temporal. Los documentos originales deben conservarse en Google Drive; no dependas del disco local del servicio para guardar información permanente.

## Configuración en Render

En el servicio del backend:

1. Abre **Environment**.
2. Agrega cada variable con el mismo nombre usado en `.env`.
3. Guarda los cambios y espera el nuevo despliegue.
4. Prueba `GET /health`.
5. Prueba chat y una operación de Drive.
6. Revisa los logs si falla alguna integración.

Nunca pegues claves o tokens en el código, README, capturas públicas o commits.

## Diagnóstico rápido

- Error por `GROQ_API_KEY`: revisa la clave y el nombre exacto de la variable.
- Error `model_not_found`: revisa el identificador configurado en `GROQ_MODEL` u `OPENAI_MODEL`.
- Error por `GOOGLE_DRIVE_FOLDER_ID`: confirma que el ID corresponde a la carpeta raíz.
- Error de credenciales OAuth: genera o copia nuevamente el token autorizado.
- Se crea carpeta pero no se suben archivos: revisa permisos de Drive y cuota de almacenamiento de la identidad usada.
- El Excel desaparece después de reiniciar Render: es comportamiento esperado del disco temporal; la fuente permanente debe ser Drive.
