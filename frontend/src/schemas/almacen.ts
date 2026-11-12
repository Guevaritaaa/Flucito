/**
 * Contratos de datos para operaciones de Almacén y Google Drive.
 * Espejo de backend/app/api/v1/routes/almacen.py
 */

export interface UploadDocumentosResponse {
  ok: boolean;
  subidos: number;
  facturas?: number;
  detalle?: unknown;
  [key: string]: unknown;
}
