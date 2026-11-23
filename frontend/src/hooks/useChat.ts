import { useCallback, useEffect, useRef, useState } from "react";
import type { ActividadChat, ReporteHistoricoItem, InteraccionDecision, RevisionReporte, EnvioDecisiones } from "../schemas/chat";
import {
  enviarMensajeChat,
  obtenerDetalleConversacion,
  obtenerSolicitudPendiente,
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
  actividades?: ActividadChat[];
  interaccion?: InteraccionDecision | null;
  revision_reporte?: RevisionReporte | null;
}

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
  const [mensajes, setMensajes] = useState<MensajeUI[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [actividades, setActividades] = useState<ActividadChat[]>([]);
  const [textoProvisional, setTextoProvisional] = useState("");
  const [etapa, setEtapa] = useState<"pensando" | "trabajando">("pensando");
  const [cargandoMensajes, setCargandoMensajes] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const ultimaSesionCargadaRef = useRef<string | null>(null);
  const reanudadaRef = useRef<string | null>(null);

  // Cargar mensajes si el usuario selecciona una conversación guardada en BD
  useEffect(() => {
    abortControllerRef.current?.abort();
    setEnviando(false);
    setActividades([]);
    setTextoProvisional("");
    setEtapa("pensando");

    if (!existeEnHistorial) {
      ultimaSesionCargadaRef.current = sessionId;
      setMensajes([]);
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
          setMensajes([]);
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
          actividades: m.actividades ?? [],
          interaccion: m.interaccion,
          revision_reporte: m.revision_reporte,
        }));
        setMensajes(mapeados);
      })
      .catch((err) => {
        if (cancelado) return;
        if (err instanceof ApiError && err.status === 404) {
          setMensajes([]);
        } else {
          setMensajes([
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
          ultimaSesionCargadaRef.current = sessionId;
          setCargandoMensajes(false);
        }
      });

    return () => {
      cancelado = true;
    };
  }, [sessionId, existeEnHistorial]);

  const enviarMensaje = useCallback(
    async (textoRaw: string, decisiones?: EnvioDecisiones) => {
      const texto = textoRaw.trim();
      if (!texto || enviando) return;

      const msgUsuario: MensajeUI = {
        id: `user-${Date.now()}`,
        rol: "user",
        contenido: texto,
        hora: formatearHora(),
      };

      const reanudando = Boolean(obtenerSolicitudPendiente(sessionId));
      setMensajes((prev) => reanudando && prev.some((m) => m.rol === "user" && m.contenido === texto) ? prev : [...prev, msgUsuario]);
      setEnviando(true);
      setActividades([]);
      setTextoProvisional("");
      setEtapa("pensando");

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const respuesta = await enviarMensajeChat(
          {
            mensaje: texto,
            session_id: sessionId,
            decisiones,
          },
          controller.signal,
          (progreso) => {
            if (abortControllerRef.current !== controller || controller.signal.aborted) return;
            setEtapa(progreso.etapa ?? "pensando");
            setActividades(progreso.actividades ?? []);
            setTextoProvisional(progreso.texto_provisional ?? "");
          }
        );
        if (controller.signal.aborted) return;

        const msgAsistente: MensajeUI = {
          id: `assistant-${Date.now()}`,
          rol: "assistant",
          contenido: respuesta.respuesta,
          hora: formatearHora(),
          archivo_almacen_url: respuesta.archivo_almacen_url,
          archivo_txt_url: respuesta.archivo_txt_url,
          reportes_historicos: respuesta.reportes_historicos ?? [],
          actividades: respuesta.actividades ?? [],
          interaccion: respuesta.interaccion,
          revision_reporte: respuesta.revision_reporte,
        };

        setMensajes((prev) => reanudando && prev.at(-1)?.contenido === msgAsistente.contenido ? prev : [...prev, msgAsistente]);
        onConversacionActualizada();
      } catch (err) {
        if (controller.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) {
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
        if (decisiones) throw err;
      } finally {
        if (abortControllerRef.current === controller) {
          setEnviando(false);
        }
      }
    },
    [sessionId, enviando, onConversacionActualizada]
  );

  useEffect(() => {
    const pendiente = obtenerSolicitudPendiente(sessionId);
    if (pendiente && ultimaSesionCargadaRef.current === sessionId && !cargandoMensajes && !enviando && reanudadaRef.current !== pendiente.jobId) {
      reanudadaRef.current = pendiente.jobId;
      void enviarMensaje(pendiente.mensaje, pendiente.decisiones).catch(() => {});
    }
  }, [sessionId, cargandoMensajes, enviando, enviarMensaje]);

  useEffect(() => {
    const reconectar = () => {
      const pendiente = obtenerSolicitudPendiente(sessionId);
      if (pendiente && !enviando) void enviarMensaje(pendiente.mensaje, pendiente.decisiones).catch(() => {});
    };
    window.addEventListener("online", reconectar);
    return () => window.removeEventListener("online", reconectar);
  }, [sessionId, enviando, enviarMensaje]);

  return {
    mensajes,
    enviando,
    actividades,
    textoProvisional,
    etapa,
    cargandoMensajes,
    enviarMensaje,
  };
}
