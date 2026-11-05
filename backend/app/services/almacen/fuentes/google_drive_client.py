"""Cliente para listar, descargar y subir documentos a Google Drive."""

from __future__ import annotations

import json
import re
from datetime import datetime
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
PREFIJO_REPORTE = "ENTRADAS_ALMACEN_"
CARPETA_ENTRADAS_AL_INVENTARIO = "ENTRADAS AL INVENTARIO"
CARPETA_REPORTES_HISTORICOS = "DOCUMENTOS ENTRADA"
NOMBRES_MESES_ES: dict[int, str] = {
    1: "ENERO",
    2: "FEBRERO",
    3: "MARZO",
    4: "ABRIL",
    5: "MAYO",
    6: "JUNIO",
    7: "JULIO",
    8: "AGOSTO",
    9: "SEPTIEMBRE",
    10: "OCTUBRE",
    11: "NOVIEMBRE",
    12: "DICIEMBRE",
}
_MESES_VALIDOS_SET = set(NOMBRES_MESES_ES.values())
_PADRES_CACHE: dict[str, str] = {}


class GoogleDriveConfigError(RuntimeError):
    """Configuración o dependencias de Google Drive ausentes."""


def crear_cliente_drive() -> Any:
    """Crea cliente Drive usando JSON de cuenta de servicio en configuración."""
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
                .execute(num_retries=3)
            )
        except Exception as error:
            status_code = getattr(getattr(error, "resp", None), "status", None)
            if status_code == 403:
                raise GoogleDriveConfigError(
                    "Google Drive API deshabilitada o sin permisos en el proyecto de la cuenta"
                ) from error
            raise
        lote = respuesta.get("files", [])
        for item in lote:
            item_id = item.get("id")
            if item_id:
                padres = item.get("parents")
                _PADRES_CACHE[item_id] = ",".join(padres) if padres else carpeta_id
        archivos.extend(lote)
        pagina = respuesta.get("nextPageToken")
        if not pagina:
            return archivos


def listar_carpetas_factura(
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> list[CarpetaFactura]:
    """Lista subcarpetas y agrupa sus XML/PDF/TXT asociados."""
    cliente = cliente or crear_cliente_drive()
    root_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not root_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    elementos = _listar_hijos(cliente, root_id)
    carpetas = [elemento for elemento in elementos if elemento.get("mimeType") == MIME_CARPETA]
    archivos: list[dict] = []
    for carpeta in carpetas:
        archivos.extend(_listar_hijos(cliente, carpeta["id"]))

    return agrupar_por_carpeta(carpetas, archivos)


def buscar_carpeta_hija(cliente: Any, nombre: str, carpeta_padre: str) -> str | None:
    """Busca una carpeta directa con el nombre indicado y devuelve su ID."""
    for elemento in _listar_hijos(cliente, carpeta_padre):
        if elemento.get("mimeType") == MIME_CARPETA and elemento.get("name") == nombre:
            return elemento["id"]
    return None


def normalizar_fecha_reporte(fecha: str) -> str:
    """Normaliza fechas aceptadas a DD-MM-AAAA, el formato de las carpetas de carga."""
    for formato in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(fecha.strip(), formato).strftime("%d-%m-%Y")
        except ValueError:
            continue
    raise ValueError("Usa una fecha válida en formato DD-MM-AAAA o AAAA-MM-DD")


def extraer_anio_mes_de_fecha_carpeta(nombre: str) -> tuple[str, str] | None:
    """Extrae (AÑO, MES_EN_MAYUSCULAS) si el nombre de carpeta representa una fecha válida."""
    limpio = str(nombre or "").strip()
    if not limpio:
        return None
    for formato in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(limpio, formato)
            return str(dt.year), NOMBRES_MESES_ES[dt.month]
        except ValueError:
            continue
    return None


def es_carpeta_anio(nombre: str) -> bool:
    """Indica si el nombre corresponde a una carpeta contenedora de año (ej. '2026', '2027')."""
    return bool(re.match(r"^(19|20)\d{2}$", str(nombre or "").strip()))


def _normalizar_nombre_mes(nombre: str) -> str | None:
    """Devuelve el nombre canónico del mes en español si coincide (con o sin prefijo numérico)."""
    limpio = str(nombre or "").strip().upper()
    if limpio in _MESES_VALIDOS_SET:
        return limpio
    m = re.match(r"^\d{1,2}[\.\-\s_]+([A-ZÁÉÍÓÚÑ]+)$", limpio)
    if m and m.group(1) in _MESES_VALIDOS_SET:
        return m.group(1)
    return None


def es_carpeta_mes(nombre: str) -> bool:
    """Indica si el nombre corresponde a una carpeta contenedora de mes (ej. 'SEPTIEMBRE', '10. OCTUBRE')."""
    return _normalizar_nombre_mes(nombre) is not None


def obtener_o_crear_carpeta_mes_historico(
    cliente: Any,
    carpeta_historico_id: str,
    nombre_carpeta_fecha: str,
    fn_buscar_o_crear: Any = None,
) -> str:
    """Obtiene o crea la jerarquía DOCUMENTOS ENTRADA / AÑO / MES para una carpeta de fecha.
    Si el nombre no es una fecha reconocible, devuelve carpeta_historico_id directamente.
    """
    anio_mes = extraer_anio_mes_de_fecha_carpeta(nombre_carpeta_fecha)
    if not anio_mes:
        return carpeta_historico_id
    creador = fn_buscar_o_crear or buscar_o_crear_carpeta
    anio, mes = anio_mes
    carpeta_anio_id = creador(cliente, anio, carpeta_historico_id)
    return creador(cliente, mes, carpeta_anio_id)


def listar_carpetas_fecha_en_historico(
    cliente: Any,
    carpeta_historico_id: str,
    filtro_fecha: str | None = None,
    fn_listar_hijos: Any = None,
) -> list[dict[str, Any]]:
    """Lista todas las carpetas de entrada/fecha dentro de DOCUMENTOS ENTRADA,
    soportando tanto la estructura jerárquica (AÑO/MES/DD-MM-YYYY) como carpetas planas (DD-MM-YYYY).
    """
    listador = fn_listar_hijos or _listar_hijos
    anio_mes_filtro = extraer_anio_mes_de_fecha_carpeta(filtro_fecha) if filtro_fecha else None
    resultado: list[dict[str, Any]] = []

    hijos_nivel1 = listador(cliente, carpeta_historico_id)
    for elem1 in hijos_nivel1:
        if elem1.get("mimeType") != MIME_CARPETA:
            continue
        nombre1 = elem1.get("name", "")
        if nombre1.upper().startswith("ARCHIVOS_SUELTOS_"):
            continue

        if es_carpeta_anio(nombre1):
            if anio_mes_filtro and nombre1.strip() != anio_mes_filtro[0]:
                continue
            hijos_nivel2 = listador(cliente, elem1["id"])
            for elem2 in hijos_nivel2:
                if elem2.get("mimeType") != MIME_CARPETA:
                    continue
                nombre2 = elem2.get("name", "")
                if nombre2.upper().startswith("ARCHIVOS_SUELTOS_"):
                    continue
                mes_canonico = _normalizar_nombre_mes(nombre2)
                if mes_canonico:
                    if anio_mes_filtro and mes_canonico != anio_mes_filtro[1]:
                        continue
                    hijos_nivel3 = listador(cliente, elem2["id"])
                    for elem3 in hijos_nivel3:
                        if elem3.get("mimeType") != MIME_CARPETA:
                            continue
                        nombre3 = elem3.get("name", "")
                        if nombre3.upper().startswith("ARCHIVOS_SUELTOS_"):
                            continue
                        if filtro_fecha and nombre3 != filtro_fecha:
                            continue
                        esperado = extraer_anio_mes_de_fecha_carpeta(nombre3)
                        en_jerarquia = bool(
                            esperado
                            and esperado[0] == nombre1.strip()
                            and esperado[1] == mes_canonico
                            and nombre2.strip() == mes_canonico
                        )
                        copia3 = dict(elem3)
                        copia3["padre_id"] = elem2["id"]
                        copia3["ruta_relativa"] = f"{nombre1}/{nombre2}/{nombre3}"
                        copia3["en_jerarquia_anio_mes"] = en_jerarquia
                        resultado.append(copia3)
                else:
                    if filtro_fecha and nombre2 != filtro_fecha:
                        continue
                    copia2 = dict(elem2)
                    copia2["padre_id"] = elem1["id"]
                    copia2["ruta_relativa"] = f"{nombre1}/{nombre2}"
                    copia2["en_jerarquia_anio_mes"] = False
                    resultado.append(copia2)
        elif es_carpeta_mes(nombre1):
            mes_canonico = _normalizar_nombre_mes(nombre1)
            if anio_mes_filtro and mes_canonico != anio_mes_filtro[1]:
                continue
            hijos_nivel2 = listador(cliente, elem1["id"])
            for elem2 in hijos_nivel2:
                if elem2.get("mimeType") != MIME_CARPETA:
                    continue
                nombre2 = elem2.get("name", "")
                if nombre2.upper().startswith("ARCHIVOS_SUELTOS_"):
                    continue
                if filtro_fecha and nombre2 != filtro_fecha:
                    continue
                copia2 = dict(elem2)
                copia2["padre_id"] = elem1["id"]
                copia2["ruta_relativa"] = f"{nombre1}/{nombre2}"
                copia2["en_jerarquia_anio_mes"] = False
                resultado.append(copia2)
        else:
            if filtro_fecha and nombre1 != filtro_fecha:
                continue
            copia1 = dict(elem1)
            copia1["padre_id"] = carpeta_historico_id
            copia1["ruta_relativa"] = nombre1
            copia1["en_jerarquia_anio_mes"] = False
            resultado.append(copia1)

    return resultado


def buscar_reportes_historicos(
    fecha: str | None = None,
    cliente: Any | None = None,
    proveedor: str | None = None,
) -> list[dict[str, str]]:
    """Busca reportes Excel históricos dentro de DOCUMENTOS ENTRADA, filtrando opcionalmente por fecha y/o proveedor."""
    cliente = cliente or crear_cliente_drive()
    root_id = settings.google_drive_folder_id
    if not root_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    fecha_normalizada = normalizar_fecha_reporte(fecha) if fecha and fecha.strip() else None
    filtro_proveedor = proveedor.strip().casefold() if proveedor and proveedor.strip() else None

    carpetas_archivo = [
        elemento
        for elemento in _listar_hijos(cliente, root_id)
        if elemento.get("mimeType") == MIME_CARPETA
        and elemento.get("name") == CARPETA_REPORTES_HISTORICOS
    ]

    reportes: list[dict[str, str]] = []
    for carpeta_archivo in carpetas_archivo:
        carpetas_fecha = listar_carpetas_fecha_en_historico(
            cliente,
            carpeta_archivo["id"],
            filtro_fecha=fecha_normalizada,
        )

        for carpeta_fecha in carpetas_fecha:
            nombre_fecha_carpeta = fecha_normalizada or carpeta_fecha.get("name", "")
            pendientes: list[tuple[str, str]] = [
                (carpeta_fecha["id"], carpeta_fecha.get("name", ""))
            ]
            visitadas: set[str] = set()
            while pendientes:
                carpeta_id, nombre_carpeta_actual = pendientes.pop()
                if carpeta_id in visitadas:
                    continue
                visitadas.add(carpeta_id)
                for elemento in _listar_hijos(cliente, carpeta_id):
                    if elemento.get("mimeType") == MIME_CARPETA:
                        pendientes.append((elemento["id"], elemento.get("name", "")))
                        continue
                    nombre = elemento.get("name", "")
                    if (
                        Path(nombre).suffix.lower() == ".xlsx"
                        and nombre.upper().startswith(PREFIJO_REPORTE)
                    ):
                        if filtro_proveedor:
                            coincide_archivo = filtro_proveedor in nombre.casefold()
                            coincide_carpeta = (
                                filtro_proveedor in nombre_carpeta_actual.casefold()
                            )
                            if not (coincide_archivo or coincide_carpeta):
                                continue
                        reportes.append(
                            {
                                "id": elemento["id"],
                                "nombre": nombre,
                                "fecha": nombre_fecha_carpeta,
                            }
                        )

    def _clave_fecha_desc(fecha_str: str) -> tuple[int, int, int, str]:
        m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", str(fecha_str or "").strip())
        if m:
            dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return (-yyyy, -mm, -dd, fecha_str)
        return (0, 0, 0, str(fecha_str or ""))

    return sorted(
        reportes,
        key=lambda reporte: (_clave_fecha_desc(reporte["fecha"]), reporte["nombre"].casefold()),
    )


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
            _, terminado = descarga.next_chunk(num_retries=3)
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
        .execute(num_retries=3)
    )
    carpetas = respuesta.get("files", [])
    if carpetas:
        carpeta_id = carpetas[0]["id"]
        _PADRES_CACHE[carpeta_id] = carpeta_padre
        return carpeta_id

    carpeta = (
        cliente.files()
        .create(
            body={"name": nombre, "mimeType": MIME_CARPETA, "parents": [carpeta_padre]},
            fields="id",
        )
        .execute(num_retries=3)
    )
    carpeta_id = carpeta["id"]
    _PADRES_CACHE[carpeta_id] = carpeta_padre
    return carpeta_id


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
        .execute(num_retries=3)
    )
    archivo_id = archivo["id"]
    _PADRES_CACHE[archivo_id] = carpeta_id
    return archivo_id


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
        .execute(num_retries=3)
    )
    archivos = respuesta.get("files", [])
    for item in archivos:
        item_id = item.get("id")
        if item_id:
            _PADRES_CACHE[item_id] = carpeta_id
    return archivos


def mover_archivo(
    cliente: Any,
    archivo_id: str,
    nueva_carpeta_id: str,
    carpeta_origen_id: str | None = None,
) -> None:
    """Mueve un archivo en Google Drive a una nueva carpeta evitando GET redundante si se conoce el padre."""
    padres_previos = carpeta_origen_id or _PADRES_CACHE.get(archivo_id)
    if not padres_previos:
        archivo = cliente.files().get(fileId=archivo_id, fields="parents").execute(num_retries=3)
        padres_previos = ",".join(archivo.get("parents", []))
    cliente.files().update(
        fileId=archivo_id,
        addParents=nueva_carpeta_id,
        removeParents=padres_previos,
        fields="id, parents",
    ).execute(num_retries=3)
    _PADRES_CACHE[archivo_id] = nueva_carpeta_id


def eliminar_archivo(cliente: Any, archivo_id: str) -> None:
    """Mueve un archivo o carpeta a la papelera en Google Drive."""
    try:
        cliente.files().update(fileId=archivo_id, body={"trashed": True}).execute(num_retries=3)
        _PADRES_CACHE.pop(archivo_id, None)
    except Exception as error:
        status_code = getattr(getattr(error, "resp", None), "status", None)
        if status_code == 404:
            _PADRES_CACHE.pop(archivo_id, None)
        else:
            raise


__all__ = [
    "GoogleDriveConfigError",
    "crear_cliente_drive",
    "descargar_archivo",
    "buscar_o_crear_carpeta",
    "buscar_carpeta_hija",
    "buscar_reportes_historicos",
    "normalizar_fecha_reporte",
    "CARPETA_ENTRADAS_AL_INVENTARIO",
    "CARPETA_REPORTES_HISTORICOS",
    "listar_archivos_carpeta",
    "listar_carpetas_factura",
    "subir_archivo",
    "mover_archivo",
    "eliminar_archivo",
]
