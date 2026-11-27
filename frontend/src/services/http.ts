/**
 * Cliente HTTP centralizado con inyección automática de JWT Bearer y manejo de errores.
 */

import { API_V1_PREFIX, BACKEND_BASE_URL } from "../core/config";
import { obtenerTokenGuardado } from "../core/storage";

export class ApiError extends Error {
  public readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedListener: UnauthorizedHandler | null = null;

export function registrarManejadorNoAutorizado(handler: UnauthorizedHandler | null): void {
  unauthorizedListener = handler;
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipAuth?: boolean;
  skipUnauthorizedHook?: boolean;
  responseType?: "blob";
}

export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { body, headers: customHeaders, skipAuth = false, skipUnauthorizedHook = false, responseType, ...rest } =
    options;

  const url = endpoint.startsWith("http")
    ? endpoint
    : `${API_V1_PREFIX}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  const headers = new Headers(customHeaders);

  if (!skipAuth) {
    const token = obtenerTokenGuardado();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  let serializedBody: BodyInit | undefined;
  if (body instanceof FormData || typeof body === "string" || body instanceof Blob) {
    serializedBody = body;
  } else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    serializedBody = JSON.stringify(body);
  }

  const response = await fetch(url, {
    ...rest,
    headers,
    body: serializedBody,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  if (response.ok && responseType === "blob") {
    return (await response.blob()) as T;
  }

  let data: unknown = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await response.json().catch(() => null);
  } else {
    data = await response.text().catch(() => null);
  }

  if (!response.ok) {
    if (response.status === 401 && !skipUnauthorizedHook && unauthorizedListener) {
      unauthorizedListener();
    }

    let detail = `Error del servidor (${response.status})`;
    if (data && typeof data === "object" && "detail" in data) {
      const rawDetail = (data as { detail: unknown }).detail;
      if (typeof rawDetail === "string") {
        detail = rawDetail;
      } else if (Array.isArray(rawDetail) && rawDetail.length > 0) {
        const first = rawDetail[0] as { msg?: string };
        if (first?.msg) detail = first.msg;
      } else if (rawDetail && typeof rawDetail === "object" && "errores" in rawDetail) {
        const errores = (rawDetail as { errores: { producto: string; campo: string; motivo: string }[] }).errores;
        detail = errores.map(e => `${e.producto} · ${e.campo}: ${e.motivo}`).join("\n");
      } else if (rawDetail && typeof rawDetail === "object" && "mensaje" in rawDetail && typeof rawDetail.mensaje === "string") {
        detail = rawDetail.mensaje;
      }
    }
    throw new ApiError(detail, response.status);
  }

  return data as T;
}

/**
 * Despierta el backend de manera silenciosa al abrir la aplicación.
 */
export function despertarBackend(): void {
  const pingUrl = BACKEND_BASE_URL || "/api/v1/auth/me";
  fetch(pingUrl, { method: "GET" }).catch(() => {
    // Silencioso en caso de arranque en frío
  });
}
