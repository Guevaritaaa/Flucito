/**
 * Configuración base del frontend (equivalente a backend/app/core/config.py).
 * Centraliza la resolución de endpoints, activos multimedia WebP/SVG/PNG y constantes de sesión.
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

/** Activos multimedia oficiales en public/Recursos */
export const ASSETS = {
  FLUCITO_AVATAR: "/Recursos/FlucitoPerfil.webp",
  FLUCITO_3D: "/Recursos/flucito-mascota-3d.webp",
  INTERFLU_LOGO: "/Recursos/LogoInterflu.svg",
  INTERFLU_LOGO_DARK: "/Recursos/LogoInterfluDark.svg",
  ENGRANAJE_METALICO: "/Recursos/engranaje-metalico.webp",
  ENGRANAJE_AZUL: "/Recursos/engranaje-azul.webp",
  ENGRANAJE_CELESTE: "/Recursos/engranaje-celeste.webp",
  GOTA_AZUL: "/Recursos/gota-azul.webp",
  GOTA_CELESTE: "/Recursos/gota-celeste.webp",
  SALPICADURA_AGUA: "/Recursos/salpicadura-agua.webp",
  ESPIRAL_CELESTE: "/Recursos/espiral-celeste.webp",
} as const;

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
