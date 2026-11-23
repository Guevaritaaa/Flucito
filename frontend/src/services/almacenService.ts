/**
 * Servicio de Almacén y Google Drive.
 * Consume /api/v1/almacen/* (backend/app/api/v1/routes/almacen.py)
 */

import { API_V1_PREFIX, resolverUrlBackend } from "../core/config";
import type { UploadDocumentosResponse } from "../schemas/almacen";
import { apiFetch } from "./http";

export async function subirDocumentosDrive(
  archivos: File[]
): Promise<UploadDocumentosResponse> {
  const formData = new FormData();
  for (const archivo of archivos) {
    formData.append("archivos", archivo);
  }
  return apiFetch<UploadDocumentosResponse>("/almacen/upload", {
    method: "POST",
    body: formData,
  });
}

export function resolverUrlDescarga(rutaRelativa: string): string {
  return resolverUrlBackend(rutaRelativa);
}

export async function descargarArchivo(ruta: string, nombre: string): Promise<void> {
  const url = new URL(resolverUrlBackend(ruta));
  const apiBase = new URL(API_V1_PREFIX, window.location.origin);
  const esRevision = new RegExp(`^${apiBase.pathname}/almacen/reportes/[a-f0-9]{32}/archivo$`).test(url.pathname);
  if (url.origin !== apiBase.origin || (!esRevision && !["", "/txt", "/historico"].some((sufijo) => url.pathname === `${apiBase.pathname}/almacen/download${sufijo}`))) {
    throw new Error("La dirección de descarga no es válida.");
  }

  const archivo = await apiFetch<Blob>(url.toString(), { responseType: "blob" });
  const objectUrl = URL.createObjectURL(archivo);
  const enlace = document.createElement("a");
  enlace.href = objectUrl;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
