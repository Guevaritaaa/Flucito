/**
 * Servicio de Chat e Historial de Conversaciones por Usuario.
 * Consume /api/v1/chat/* (backend/app/api/v1/routes/chat.py)
 */

import type {
  ChatJobCreateResponse,
  ChatJobStatusResponse,
  ChatRequest,
  ChatResponse,
  ConversacionDetalleOut,
  ConversacionResumenOut,
} from "../schemas/chat";
import { ApiError, apiFetch } from "./http";
import { API_V1_PREFIX } from "../core/config";
import { obtenerTokenGuardado } from "../core/storage";

class ChatJobError extends Error {}

const clavePendiente = (sessionId: string) => `flucito_job:${sessionId}`;
function limpiarSolicitudPendiente(sessionId: string) {
  try { sessionStorage.removeItem(clavePendiente(sessionId)); } catch { /* El resultado sigue siendo válido si el almacenamiento está bloqueado. */ }
}
export function obtenerSolicitudPendiente(sessionId: string): (ChatRequest & { jobId: string }) | null {
  try {
    const valor = sessionStorage.getItem(clavePendiente(sessionId));
    return valor ? JSON.parse(valor) : null;
  } catch { return null; }
}

async function escucharProgreso(jobId: string, signal?: AbortSignal, onProgreso?: (estado: ChatJobStatusResponse) => void): Promise<ChatResponse> {
  const headers = new Headers({ Accept: "text/event-stream" });
  const token = obtenerTokenGuardado();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_V1_PREFIX}/chat/events/${encodeURIComponent(jobId)}`, { headers, signal });
  if (!response.ok) throw new ApiError("No se pudo conectar a la actividad", response.status);
  if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) throw new Error("Streaming no disponible");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
        if (!data) continue;
        const estado = JSON.parse(data) as ChatJobStatusResponse;
        onProgreso?.(estado);
        if (estado.status === "completed" && estado.result) return estado.result;
        if (estado.status === "failed") throw new ChatJobError(estado.error || "Error procesando solicitud en Flucito");
      }
    }
    throw new Error("Conexión de actividad interrumpida");
  } finally {
    await reader.cancel().catch(() => {});
  }
}

function esperar(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener(
        "abort",
        () => {
          window.clearTimeout(timer);
          reject(new DOMException("Operación cancelada", "AbortError"));
        },
        { once: true }
      );
    }
  });
}

export async function enviarMensajeSincrono(
  payload: ChatRequest,
  signal?: AbortSignal
): Promise<ChatResponse> {
  return apiFetch<ChatResponse>("/chat", {
    method: "POST",
    body: payload,
    signal,
  });
}

export async function iniciarChatAsync(
  payload: ChatRequest,
  signal?: AbortSignal
): Promise<ChatJobCreateResponse> {
  return apiFetch<ChatJobCreateResponse>("/chat/async", {
    method: "POST",
    body: payload,
    signal,
  });
}

export async function consultarEstadoChat(
  jobId: string,
  signal?: AbortSignal
): Promise<ChatJobStatusResponse> {
  return apiFetch<ChatJobStatusResponse>(`/chat/status/${encodeURIComponent(jobId)}`, {
    method: "GET",
    signal,
  });
}

/**
 * Ejecuta el flujo asíncrono (/chat/async + polling en /chat/status/{job_id})
 * con respaldo automático al endpoint síncrono (/chat) si es necesario.
 */
async function ejecutarMensajeChat(
  payload: ChatRequest,
  signal?: AbortSignal,
  onProgreso?: (estado: ChatJobStatusResponse) => void
): Promise<ChatResponse> {
  const pendiente = obtenerSolicitudPendiente(payload.session_id);
  let jobId: string | undefined = pendiente?.jobId;
  if (pendiente && (pendiente.mensaje !== payload.mensaje || JSON.stringify(pendiente.decisiones) !== JSON.stringify(payload.decisiones))) throw new Error("Hay una solicitud en curso. Espera su resultado antes de enviar otra.");
  try {
    if (!jobId) {
      const inicio = await iniciarChatAsync(payload, signal);
      jobId = inicio.job_id;
      try { sessionStorage.setItem(clavePendiente(payload.session_id), JSON.stringify({ ...payload, jobId })); } catch { /* Puede continuar aunque el navegador no permita almacenamiento. */ }
    }
  } catch (err) {
    if (signal?.aborted || (err instanceof DOMException && err.name === "AbortError")) {
      throw err;
    }
    if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
      throw err;
    }
    if (err instanceof ApiError && (err.status === 404 || err.status === 405)) return enviarMensajeSincrono(payload, signal);
    throw err;
  }

  if (!jobId) {
    throw new Error("No se recibió el identificador de la solicitud.");
  }

  try {
    return await escucharProgreso(jobId, signal, onProgreso);
  } catch (err) {
    if (signal?.aborted || err instanceof ChatJobError || (err instanceof ApiError && (err.isUnauthorized || err.isForbidden))) throw err;
    // El trabajo sigue en el servidor; consultar el mismo identificador evita repetirlo.
  }

  let intentos = 0;
  let erroresRedConsecutivos = 0;

  while (true) {
    const pausaMs = intentos === 0 ? 600 : intentos === 1 ? 1200 : 2500;
    intentos += 1;
    await esperar(pausaMs, signal);

    try {
      const estado = await consultarEstadoChat(jobId, signal);
      erroresRedConsecutivos = 0;
      onProgreso?.(estado);

      if (estado.status === "completed" && estado.result) {
        return estado.result;
      }
      if (estado.status === "failed") {
        throw new ChatJobError(estado.error || "Error procesando solicitud en Flucito");
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw err;
      }
      if (err instanceof ApiError) {
        if (err.status === 404) {
          throw new ChatJobError("La tarea ya no está disponible. Revisa el historial antes de volver a enviarla.");
        }
        if (err.isUnauthorized || err.isForbidden) {
          throw err;
        }
      }
      if (err instanceof ChatJobError) {
        throw err;
      }
      erroresRedConsecutivos += 1;
      if (erroresRedConsecutivos >= 8) {
        throw err;
      }
    }
  }
}

export async function enviarMensajeChat(payload: ChatRequest, signal?: AbortSignal, onProgreso?: (estado: ChatJobStatusResponse) => void): Promise<ChatResponse> {
  try {
    const resultado = await ejecutarMensajeChat(payload, signal, onProgreso);
    limpiarSolicitudPendiente(payload.session_id);
    return resultado;
  } catch (error) {
    if (error instanceof ChatJobError || (error instanceof ApiError && (error.isUnauthorized || error.isForbidden))) {
      limpiarSolicitudPendiente(payload.session_id);
    }
    throw error;
  }
}

export async function listarConversaciones(): Promise<ConversacionResumenOut[]> {
  return apiFetch<ConversacionResumenOut[]>("/chat/conversaciones", {
    method: "GET",
  });
}

export async function obtenerDetalleConversacion(
  sessionId: string
): Promise<ConversacionDetalleOut> {
  return apiFetch<ConversacionDetalleOut>(
    `/chat/conversaciones/${encodeURIComponent(sessionId)}`,
    {
      method: "GET",
    }
  );
}

export async function eliminarConversacion(sessionId: string): Promise<void> {
  return apiFetch<void>(`/chat/conversaciones/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}
