import { useCallback, useEffect, useRef, useState } from "react";
import type { ReporteHistoricoItem } from "../schemas/chat";
import {
  enviarMensajeChat,
  obtenerDetalleConversacion,
} from "../services/chatService";
import { ApiError } from "../services/http";

export interface MensajeUI {
  id: string;
  rol: "user" | "assistant";
  contenido: string;
  hora: string;
  archivo_almacen_url?: string | null;
  archivo_txt_url?: string | null;
  reportes_historicos?: ReporteHistoricoItem[];
  esError?: boolean;
}

const MENSAJE_BIENVENIDA_TEXTO =
  "¡Hola! Soy Flucito :), tu asistente en Interflu. Estoy conectado al catálogo maestro de Aspel SAE y a las carpetas de Google Drive para ayudarte a consultar artículos, factores de precio y generar tus reportes de almacén. ¿En qué te puedo ayudar hoy?";

function formatearHora(isoOrDate?: string | Date): string {
  try {
    const fecha = isoOrDate ? new Date(isoOrDate) : new Date();
    return fecha.toLocaleTimeString("es-MX", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function crearMensajeBienvenida(): MensajeUI {
  return {
    id: "welcome-msg",
    rol: "assistant",
    contenido: MENSAJE_BIENVENIDA_TEXTO,
    hora: formatearHora(),
  };
}

interface UseChatOptions {
  sessionId: string;
  existeEnHistorial: boolean;
  onConversacionActualizada: () => void;
}

export function useChat({
  sessionId,
  existeEnHistorial,
  onConversacionActualizada,
}: UseChatOptions) {
  const [mensajes, setMensajes] = useState<MensajeUI[]>(() => [
    crearMensajeBienvenida(),
  ]);
  const [enviando, setEnviando] = useState(false);
  const [cargandoMensajes, setCargandoMensajes] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const ultimaSesionCargadaRef = useRef<string | null>(null);

  // Cargar mensajes si el usuario selecciona una conversación guardada en BD
  useEffect(() => {
    abortControllerRef.current?.abort();
    setEnviando(false);

    if (!existeEnHistorial) {
      ultimaSesionCargadaRef.current = sessionId;
      setMensajes([crearMensajeBienvenida()]);
      setCargandoMensajes(false);
      return;
    }

    let cancelado = false;
    setCargandoMensajes(true);

    obtenerDetalleConversacion(sessionId)
      .then((detalle) => {
        if (cancelado) return;
        ultimaSesionCargadaRef.current = sessionId;
        if (!detalle.mensajes || detalle.mensajes.length === 0) {
          setMensajes([crearMensajeBienvenida()]);
          return;
        }
        const mapeados: MensajeUI[] = detalle.mensajes.map((m) => ({
          id: `db-${m.id}`,
          rol: m.rol === "user" ? "user" : "assistant",
          contenido: m.contenido,
          hora: formatearHora(m.creado_en),
          archivo_almacen_url: m.archivo_almacen_url,
          archivo_txt_url: m.archivo_txt_url,
          reportes_historicos: m.reportes_historicos ?? [],
        }));
        setMensajes(mapeados);
      })
      .catch((err) => {
        if (cancelado) return;
        if (err instanceof ApiError && err.status === 404) {
          setMensajes([crearMensajeBienvenida()]);
        } else {
          setMensajes([
            crearMensajeBienvenida(),
            {
              id: `err-load-${Date.now()}`,
              rol: "assistant",
              contenido:
                "No se pudieron recuperar los mensajes anteriores de esta sesión.",
              hora: formatearHora(),
              esError: true,
            },
          ]);
        }
      })
      .finally(() => {
        if (!cancelado) {
          setCargandoMensajes(false);
        }
      });

    return () => {
      cancelado = true;
    };
  }, [sessionId, existeEnHistorial]);

  const enviarMensaje = useCallback(
    async (textoRaw: string) => {
      const texto = textoRaw.trim();
      if (!texto || enviando) return;

      const msgUsuario: MensajeUI = {
        id: `user-${Date.now()}`,
        rol: "user",
        contenido: texto,
        hora: formatearHora(),
      };

      setMensajes((prev) => [...prev, msgUsuario]);
      setEnviando(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const respuesta = await enviarMensajeChat(
          {
            mensaje: texto,
            session_id: sessionId,
          },
          controller.signal
        );

        const msgAsistente: MensajeUI = {
          id: `assistant-${Date.now()}`,
          rol: "assistant",
          contenido: respuesta.respuesta,
          hora: formatearHora(),
          archivo_almacen_url: respuesta.archivo_almacen_url,
          archivo_txt_url: respuesta.archivo_txt_url,
          reportes_historicos: respuesta.reportes_historicos ?? [],
        };

        setMensajes((prev) => [...prev, msgAsistente]);
        onConversacionActualizada();
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        const detalleError =
          err instanceof Error && err.message
            ? err.message
            : "Hubo un error al contactar a Flucito. Intenta de nuevo.";

        setMensajes((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            rol: "assistant",
            contenido: detalleError,
            hora: formatearHora(),
            esError: true,
          },
        ]);
      } finally {
        if (abortControllerRef.current === controller) {
          setEnviando(false);
        }
      }
    },
    [sessionId, enviando, onConversacionActualizada]
  );

  return {
    mensajes,
    enviando,
    cargandoMensajes,
    enviarMensaje,
  };
}
