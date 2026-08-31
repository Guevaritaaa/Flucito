# Configuración del entorno

Flucito necesita algunos datos para conectarse a los modelos de IA y a Google Drive. Esos datos se llaman variables de entorno.

En local se escriben en `backend/.env`. En Render se agregan en la sección **Environment** del servicio. El archivo `.env` contiene información privada y nunca debe subirse a Git.

## Antes de configurar

Hay cuatro conceptos distintos:

- **Clave API:** contraseña que permite usar un proveedor de IA.
- **Modelo:** nombre exacto del modelo que se solicitará al proveedor.
- **ID de carpeta:** identificador de una carpeta específica de Google Drive.
- **Credencial OAuth/token:** archivos o JSON que permiten a Flucito actuar sobre el Drive autorizado.

No son intercambiables. Por ejemplo, el ID de carpeta no permite conectarse a Drive por sí solo, y el JSON OAuth no sustituye al ID de la carpeta donde se guardarán los documentos.

## Configuración local

Desde la carpeta `backend`:

```powershell
Copy-Item .env.example .env
```

Abre `backend/.env` y reemplaza los valores de ejemplo. Para iniciar la API, también debes ejecutar el comando desde `backend`, para que la aplicación encuentre ese `.env`.

## Variables de modelos de IA

```env
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
LLM_PRIMARY_PROVIDER=groq
LLM_FALLBACK_ENABLED=true
```

### `GROQ_API_KEY`

Clave privada creada en la cuenta de Groq. Se obtiene desde el panel de Groq, en la sección de API keys. Permite que Flucito envíe mensajes al modelo de Groq.

### `GROQ_MODEL`

Identificador exacto del modelo disponible en Groq. No es un nombre inventado ni el nombre comercial que aparece en una conversación. Si el identificador no existe, Render mostrará un error `model_not_found`.

### `OPENAI_API_KEY`

Clave privada de la API de OpenAI. Flucito la utiliza como proveedor alternativo cuando Groq falla y `LLM_FALLBACK_ENABLED=true`.

### `OPENAI_MODEL`

Identificador exacto del modelo de OpenAI que se usará como respaldo. Debe coincidir con un modelo al que la cuenta tenga acceso.

### `LLM_PRIMARY_PROVIDER`

Indica cuál proveedor se intenta primero. Los valores válidos son:

```env
LLM_PRIMARY_PROVIDER=groq
```

También puede ser `openai`.

### `LLM_FALLBACK_ENABLED`

Activa o desactiva el cambio automático de proveedor:

```env
LLM_FALLBACK_ENABLED=true
```

Con `true`, Flucito intenta el segundo proveedor ante errores recuperables, como modelo no disponible, límite de peticiones o error temporal. El fallback no soluciona una clave inválida si ambas claves están mal.

## Variables de Google Drive

```env
GOOGLE_DRIVE_FOLDER_ID=...
GOOGLE_OAUTH_CLIENT_JSON=...
GOOGLE_OAUTH_TOKEN_JSON=...
```

### `GOOGLE_DRIVE_FOLDER_ID`

Es el ID de una carpeta real de Google Drive. Esa carpeta funciona como raíz: Flucito la usa como punto de partida para crear subcarpetas, subir XML/PDF/TXT y buscar documentos pendientes.

Para obtenerlo:

1. Abre Google Drive con la cuenta que autorizaste para Flucito.
2. Crea o localiza la carpeta que se usará para los documentos.
3. Entra a esa carpeta.
4. Copia el texto que aparece en la URL después de `/folders/`.

Ejemplo:

```text
https://drive.google.com/drive/u/0/folders/1AbC_defGHIjKlmNop
```

El valor sería:

```env
GOOGLE_DRIVE_FOLDER_ID=1AbC_defGHIjKlmNop
```

No copies la URL completa, solo el identificador. La cuenta autenticada debe tener permiso para ver, crear y subir archivos dentro de esa carpeta.

### `GOOGLE_OAUTH_CLIENT_JSON`

Es el contenido completo del archivo JSON que se descarga desde Google Cloud al crear un cliente OAuth. Describe la aplicación autorizada; no es el ID de la carpeta ni el token del usuario.

En Render se pega el JSON completo como valor de la variable. Debe conservar su estructura JSON. No lo publiques ni lo agregues al repositorio.

### `GOOGLE_OAUTH_TOKEN_JSON`

Es el token generado después de autorizar la aplicación OAuth con la cuenta de Google que posee o administra la carpeta. Permite que Flucito use Drive sin pedir autorización en cada ejecución.

En Render se pega el contenido completo del token como valor de la variable. Si el token se revoca, caduca por las políticas de Google o se cambia el acceso concedido, debe generarse otro.

OAuth es la opción recomendada para trabajar con el Drive personal del usuario. La cuenta autenticada debe tener acceso a la carpeta indicada por `GOOGLE_DRIVE_FOLDER_ID`.

## OAuth local mediante archivos

En local pueden usarse archivos en vez de pegar JSON dentro de `.env`:

```env
GOOGLE_OAUTH_CLIENT_FILE=ruta/al/cliente_oauth.json
GOOGLE_OAUTH_TOKEN_FILE=token_drive.json
```

`GOOGLE_OAUTH_CLIENT_FILE` apunta al JSON descargado desde Google Cloud. `GOOGLE_OAUTH_TOKEN_FILE` indica dónde guardar el token después de autorizar.

Esos archivos deben permanecer fuera de Git. Si se ejecuta OAuth localmente, el navegador abrirá el flujo de autorización y el token quedará guardado en la ruta indicada.

## Cuenta de servicio

Como alternativa, puede usarse una cuenta de servicio:

```env
GOOGLE_SERVICE_ACCOUNT_JSON=...
GOOGLE_SERVICE_ACCOUNT_FILE=ruta/al/service-account.json
```

Una cuenta de servicio es una identidad técnica separada de una cuenta personal. Para usarla, comparte la carpeta de Google Drive con el correo de la cuenta de servicio y dale permisos suficientes.

Sus capacidades dependen del permiso otorgado en esa carpeta:

- **Lector:** puede consultar y descargar archivos, pero no crear carpetas ni subir documentos.
- **Comentador:** puede agregar comentarios, pero no administrar la estructura ni cargar archivos como necesita Flucito.
- **Editor:** puede leer, crear carpetas y subir o modificar archivos dentro de la carpeta compartida.

Por eso, una cuenta de servicio con permiso de Editor sí puede ejecutar el flujo completo dentro de una carpeta compartida. El problema habitual aparece al intentar subir archivos al Drive personal: la cuenta de servicio tiene identidad y cuota propias, por lo que puede no tener almacenamiento disponible aunque la carpeta pertenezca a otra cuenta. OAuth suele ser más conveniente cuando los archivos deben guardarse en el Drive personal del usuario.

### Lo que ocurrió en Flucito

Durante las primeras pruebas, la cuenta de servicio podía autenticarse y trabajar con la estructura de la carpeta, pero no lograba completar correctamente la carga de archivos. La causa no era que una cuenta de servicio fuera obligatoriamente de solo lectura, sino la diferencia entre sus permisos y su cuota de almacenamiento.

Por eso se cambió a OAuth. OAuth permite que Flucito actúe con la cuenta personal autorizada, usando su acceso y almacenamiento de Google Drive. Para este proyecto, esa configuración resultó más adecuada para crear carpetas y subir documentos al Drive personal.

No mezcles OAuth y cuenta de servicio sin una razón concreta. El cliente de Flucito prioriza OAuth cuando existe configuración OAuth.

## Testing y Production en OAuth

Google distingue entre el estado **Testing** y **In production** de la pantalla de consentimiento OAuth.

Cuando una aplicación externa está en **Testing**, los refresh tokens para permisos como Drive tienen una duración limitada; en el caso que afectó a Flucito, el token dejó de funcionar después de 7 días. Google documenta esta limitación para aplicaciones en pruebas.

Al cambiar la aplicación a **In production** y volver a autorizarla, los refresh tokens ya no tienen normalmente ese límite automático de 7 días. Esto no significa que sean eternos: pueden invalidarse si el usuario revoca el acceso, cambia ciertas configuraciones de seguridad, se alcanza un límite de tokens o permanecen sin uso durante un periodo prolongado.

En Flucito se hizo lo siguiente:

1. Se cambió la pantalla de consentimiento OAuth de **Testing** a **In production**.
2. Se volvió a autorizar la aplicación con la cuenta de Google que administra la carpeta.
3. Se generó un nuevo refresh token.
4. Se guardaron el client JSON y el token en variables de entorno de Render.
5. Se verificó la carga de documentos y la generación del Excel.

Referencia: [OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview) y [Using OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server).

## Carpeta local de datos

```env
ALMACEN_CARPETA_DATOS=
```

Indica dónde guardar el Excel, resúmenes, estado de sincronización y archivos de trabajo. Si se deja vacío, Flucito usa:

```text
backend/datos/almacen
```

En Render, el disco local es temporal. Google Drive debe considerarse la ubicación permanente de los documentos originales.

## Configuración en Render

1. Abre el servicio backend de Flucito.
2. Entra a **Environment**.
3. Agrega cada variable con el mismo nombre escrito en `.env`.
4. Pega las claves y JSON como valores privados.
5. Guarda los cambios y espera el nuevo despliegue.
6. Prueba `GET https://tu-dominio.onrender.com/health`.
7. Prueba chat, carga de documentos y generación de Excel.

Render no lee automáticamente el archivo `.env` de tu computadora. Las variables deben existir también en el panel de Render.

## Diagnóstico rápido

- `GROQ_API_KEY` falla: revisa clave, espacios y nombre exacto.
- `model_not_found`: revisa el identificador configurado en `GROQ_MODEL` u `OPENAI_MODEL`.
- Falta `GOOGLE_DRIVE_FOLDER_ID`: copia solo el ID de la URL de la carpeta.
- OAuth falla: confirma que el client JSON y token pertenecen al mismo proyecto OAuth.
- Se crea carpeta pero no suben archivos: confirma que la identidad tenga permiso Editor y revisa su cuota de almacenamiento; crear carpetas y subir archivos son permisos y operaciones distintas.
- El Excel desaparece tras reiniciar Render: es normal en disco temporal; conserva documentos en Drive.
- Cambiaste variables en Render y no surte efecto: espera el redeploy o reinicia el servicio.
