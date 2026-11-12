/**
 * Servicio de Almacén y Google Drive.
 * Consume /api/v1/almacen/* (backend/app/api/v1/routes/almacen.py)
 */

import { resolverUrlBackend } from "../core/config";
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
