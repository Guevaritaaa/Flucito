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
export async function enviarMensajeChat(
  payload: ChatRequest,
  signal?: AbortSignal
): Promise<ChatResponse> {
  let jobId: string | undefined;
  try {
    const inicio = await iniciarChatAsync(payload, signal);
    jobId = inicio.job_id;
  } catch (err) {
    if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
      throw err;
    }
    return enviarMensajeSincrono(payload, signal);
  }

  if (!jobId) {
    return enviarMensajeSincrono(payload, signal);
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

      if (estado.status === "completed" && estado.result) {
        return estado.result;
      }
      if (estado.status === "failed") {
        throw new Error(estado.error || "Error procesando solicitud en Flucito");
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw err;
      }
      if (err instanceof ApiError) {
        if (err.status === 404) {
          return enviarMensajeSincrono(payload, signal);
        }
        if (err.isUnauthorized || err.isForbidden) {
          throw err;
        }
      }
      if (err instanceof Error && err.message.startsWith("Error procesando")) {
        throw err;
      }
      erroresRedConsecutivos += 1;
      if (erroresRedConsecutivos >= 8) {
        throw err;
      }
    }
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
