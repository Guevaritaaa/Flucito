"""Cliente para listar, descargar y subir documentos a Google Drive."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.almacen.fuentes.google_drive import (
    MIME_CARPETA,
    CarpetaFactura,
    DriveArchivo,
    agrupar_por_carpeta,
)


SCOPES = ["https://www.googleapis.com/auth/drive"]
ARCHIVOS_FIELDS = "nextPageToken,files(id,name,mimeType,modifiedTime,parents)"


class GoogleDriveConfigError(RuntimeError):
    """ConfiguraciÃ³n o dependencias de Google Drive ausentes."""


def crear_cliente_drive() -> Any:
    """Crea cliente Drive usando JSON de cuenta de servicio en configuraciÃ³n."""
    if not settings.google_drive_folder_id:
        raise GoogleDriveConfigError(
            "Falta GOOGLE_DRIVE_FOLDER_ID"
        )

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials as OAuthCredentials
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ModuleNotFoundError as error:
        raise GoogleDriveConfigError(
            "Instala google-api-python-client, google-auth y google-auth-oauthlib"
        ) from error

    try:
        if settings.google_oauth_client_json or settings.google_oauth_client_file:
            if settings.google_oauth_token_json:
                credenciales = OAuthCredentials.from_authorized_user_info(
                    json.loads(settings.google_oauth_token_json),
                    SCOPES,
                )
                ruta_token = None
            else:
                ruta_token = Path(settings.google_oauth_token_file)
                credenciales = None
                if ruta_token.is_file():
                    credenciales = OAuthCredentials.from_authorized_user_file(
                        ruta_token,
                        SCOPES,
                    )

            if not credenciales or not credenciales.valid:
                if credenciales and credenciales.expired and credenciales.refresh_token:
                    credenciales.refresh(Request())
                elif settings.google_oauth_client_json:
                    flujo = InstalledAppFlow.from_client_config(
                        json.loads(settings.google_oauth_client_json),
                        SCOPES,
                    )
                    credenciales = flujo.run_local_server(port=0)
                else:
                    flujo = InstalledAppFlow.from_client_secrets_file(
                        settings.google_oauth_client_file,
                        SCOPES,
                    )
                    credenciales = flujo.run_local_server(port=0)

                if ruta_token:
                    ruta_token.parent.mkdir(parents=True, exist_ok=True)
                    ruta_token.write_text(credenciales.to_json(), encoding="utf-8")
        elif settings.google_service_account_json:
            datos_cuenta = json.loads(settings.google_service_account_json)
            credenciales = ServiceAccountCredentials.from_service_account_info(
                datos_cuenta,
                scopes=SCOPES,
            )
        elif settings.google_service_account_file:
            datos_cuenta = json.loads(
                Path(settings.google_service_account_file).read_text(encoding="utf-8")
            )
            credenciales = ServiceAccountCredentials.from_service_account_info(
                datos_cuenta,
                scopes=SCOPES,
            )
        else:
            raise GoogleDriveConfigError(
                "Falta GOOGLE_OAUTH_CLIENT_FILE o credencial de cuenta de servicio"
            )
    except GoogleDriveConfigError:
        raise
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise GoogleDriveConfigError(
            "Credencial de Google no contiene JSON valido o no se puede leer"
        ) from error

    return build("drive", "v3", credentials=credenciales, cache_discovery=False)


def _listar_hijos(cliente: Any, carpeta_id: str) -> list[dict]:
    archivos: list[dict] = []
    pagina: str | None = None
    while True:
        try:
            respuesta = (
                cliente.files()
                .list(
                    q=f"'{carpeta_id}' in parents and trashed = false",
                    spaces="drive",
                    fields=ARCHIVOS_FIELDS,
                    pageSize=1000,
                    pageToken=pagina,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as error:
            status_code = getattr(getattr(error, "resp", None), "status", None)
            if status_code == 403:
                raise GoogleDriveConfigError(
                    "Google Drive API deshabilitada o sin permisos en el proyecto de la cuenta"
                ) from error
            raise
        archivos.extend(respuesta.get("files", []))
        pagina = respuesta.get("nextPageToken")
        if not pagina:
            return archivos


def listar_carpetas_factura(cliente: Any | None = None) -> list[CarpetaFactura]:
    """Lista subcarpetas y agrupa sus XML/PDF/TXT asociados."""
    cliente = cliente or crear_cliente_drive()
    root_id = settings.google_drive_folder_id
    if not root_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    elementos = _listar_hijos(cliente, root_id)
    carpetas = [elemento for elemento in elementos if elemento.get("mimeType") == MIME_CARPETA]
    archivos: list[dict] = []
    for carpeta in carpetas:
        archivos.extend(_listar_hijos(cliente, carpeta["id"]))

    return agrupar_por_carpeta(carpetas, archivos)


def descargar_archivo(cliente: Any, archivo: DriveArchivo, destino: Path) -> Path:
    """Descarga un archivo Drive a ruta temporal controlada por el proceso."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ModuleNotFoundError as error:
        raise GoogleDriveConfigError(
            "Instala google-api-python-client para descargar documentos"
        ) from error

    destino.parent.mkdir(parents=True, exist_ok=True)
    solicitud = cliente.files().get_media(fileId=archivo.id)
    with destino.open("wb") as salida:
        descarga = MediaIoBaseDownload(salida, solicitud)
        terminado = False
        while not terminado:
            _, terminado = descarga.next_chunk()
    return destino


def buscar_o_crear_carpeta(cliente: Any, nombre: str, carpeta_padre: str) -> str:
    """Devuelve carpeta hija existente o crea una nueva."""
    nombre_drive = nombre.replace("'", "\\'")
    consulta = (
        f"'{carpeta_padre}' in parents and trashed = false "
        "and mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{nombre_drive}'"
    )
    respuesta = (
        cliente.files()
        .list(q=consulta, spaces="drive", fields="files(id,name)", pageSize=10)
        .execute()
    )
    carpetas = respuesta.get("files", [])
    if carpetas:
        return carpetas[0]["id"]

    carpeta = (
        cliente.files()
        .create(
            body={"name": nombre, "mimeType": MIME_CARPETA, "parents": [carpeta_padre]},
            fields="id",
        )
        .execute()
    )
    return carpeta["id"]


def subir_archivo(cliente: Any, ruta: Path, carpeta_id: str) -> str:
    """Sube archivo local a carpeta Drive y devuelve su ID."""
    try:
        from googleapiclient.http import MediaFileUpload
    except ModuleNotFoundError as error:
        raise GoogleDriveConfigError(
            "Instala google-api-python-client para subir documentos"
        ) from error

    archivo = (
        cliente.files()
        .create(
            body={"name": ruta.name, "parents": [carpeta_id]},
            media_body=MediaFileUpload(str(ruta), resumable=True),
            fields="id",
        )
        .execute()
    )
    return archivo["id"]


def listar_archivos_carpeta(cliente: Any, carpeta_id: str) -> list[dict]:
    """Lista archivos directos de carpeta para evitar cargas duplicadas."""
    respuesta = (
        cliente.files()
        .list(
            q=f"'{carpeta_id}' in parents and trashed = false",
            spaces="drive",
            fields="files(id,name,modifiedTime)",
            pageSize=1000,
        )
        .execute()
    )
    return respuesta.get("files", [])


__all__ = [
    "GoogleDriveConfigError",
    "crear_cliente_drive",
    "descargar_archivo",
    "buscar_o_crear_carpeta",
    "listar_archivos_carpeta",
    "listar_carpetas_factura",
    "subir_archivo",
]
