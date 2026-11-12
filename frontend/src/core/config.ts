/**
 * Configuración base del frontend (equivalente a backend/app/core/config.py).
 * Centraliza la resolución de endpoints y constantes de sesión.
 */

const host = typeof window !== "undefined" ? window.location.hostname : "localhost";

export const BACKEND_BASE_URL = host.endsWith("flucito.com")
  ? "https://api.flucito.com"
  : host === "localhost" || host === "127.0.0.1"
    ? "" // En desarrollo Vite redirige /api -> http://127.0.0.1:8000
    : "";

export const API_V1_PREFIX = `${BACKEND_BASE_URL}/api/v1`;

export const AUTH_TOKEN_STORAGE_KEY = "flucito_auth_token";
export const AUTH_USER_STORAGE_KEY = "flucito_auth_user";
export const ACTIVE_SESSION_STORAGE_KEY = "flucito_active_session_id";

export function resolverUrlBackend(rutaRelativa: string): string {
  if (!rutaRelativa) return "";
  if (rutaRelativa.startsWith("http://") || rutaRelativa.startsWith("https://")) {
    return rutaRelativa;
  }
  const base =
    BACKEND_BASE_URL ||
    (typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:8000");
  return new URL(rutaRelativa, base).toString();
}
