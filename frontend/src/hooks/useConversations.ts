import { useCallback, useEffect, useState } from "react";
import {
  generarNuevoSessionId,
  guardarSessionIdActivo,
  obtenerSessionIdActivo,
} from "../core/storage";
import type { ConversacionResumenOut } from "../schemas/chat";
import {
  crearConversacionSae,
  eliminarConversacion,
  listarConversaciones,
} from "../services/chatService";

export interface UseConversationsReturn {
  conversaciones: ConversacionResumenOut[];
  sessionIdActivo: string;
  conversacionActiva: ConversacionResumenOut | null;
  cargandoHistorial: boolean;
  errorHistorial: string | null;
  iniciarNuevaConversacion: () => string;
  iniciarConversacionSae: () => Promise<string>;
  seleccionarConversacion: (sessionId: string) => void;
  borrarConversacion: (sessionId: string) => Promise<void>;
  refrescarConversaciones: (silencioso?: boolean) => Promise<void>;
}

export function useConversations(autenticado: boolean, accesoSae: boolean): UseConversationsReturn {
  const [conversaciones, setConversaciones] = useState<ConversacionResumenOut[]>([]);
  const [sessionIdActivo, setSessionIdActivo] = useState<string>(() =>
    obtenerSessionIdActivo()
  );
  const [cargandoHistorial, setCargandoHistorial] = useState<boolean>(false);
  const [errorHistorial, setErrorHistorial] = useState<string | null>(null);

  const refrescarConversaciones = useCallback(
    async (silencioso = false) => {
      if (!autenticado) {
        setConversaciones([]);
        return;
      }
      if (!silencioso) {
        setCargandoHistorial(true);
      }
      setErrorHistorial(null);
      try {
        const lista = await listarConversaciones();
        setConversaciones(lista);
      } catch {
        setErrorHistorial("No se pudo cargar el historial de conversaciones.");
      } finally {
        if (!silencioso) {
          setCargandoHistorial(false);
        }
      }
    },
    [autenticado]
  );

  useEffect(() => {
    if (autenticado) {
      void refrescarConversaciones(false);
    } else {
      setConversaciones([]);
    }
  }, [accesoSae, autenticado, refrescarConversaciones]);

  const iniciarNuevaConversacion = useCallback((): string => {
    const nuevoId = generarNuevoSessionId();
    guardarSessionIdActivo(nuevoId);
    setSessionIdActivo(nuevoId);
    return nuevoId;
  }, []);

  const seleccionarConversacion = useCallback((sessionId: string) => {
    guardarSessionIdActivo(sessionId);
    setSessionIdActivo(sessionId);
  }, []);

  const iniciarConversacionSae = useCallback(async () => {
    const conversacion = await crearConversacionSae();
    setConversaciones((previas) => [conversacion, ...previas]);
    return conversacion.id;
  }, []);

  const borrarConversacion = useCallback(
    async (sessionId: string) => {
      // Actualización optimista inmediata para respuesta táctil sin espera
      const previo = conversaciones;
      setConversaciones((actual) => actual.filter((c) => c.id !== sessionId));

      if (sessionIdActivo === sessionId) {
        const restantes = previo.filter((c) => c.id !== sessionId);
        if (restantes.length > 0) {
          guardarSessionIdActivo(restantes[0].id);
          setSessionIdActivo(restantes[0].id);
        } else {
          const nuevoId = generarNuevoSessionId();
          guardarSessionIdActivo(nuevoId);
          setSessionIdActivo(nuevoId);
        }
      }

      try {
        await eliminarConversacion(sessionId);
      } catch {
        // Revertir si hubo fallo de red
        setConversaciones(previo);
        setErrorHistorial("No fue posible eliminar la conversación.");
      }
    },
    [conversaciones, sessionIdActivo]
  );

  const conversacionActiva =
    conversaciones.find((c) => c.id === sessionIdActivo) ?? null;

  return {
    conversaciones,
    sessionIdActivo,
    conversacionActiva,
    cargandoHistorial,
    errorHistorial,
    iniciarNuevaConversacion,
    iniciarConversacionSae,
    seleccionarConversacion,
    borrarConversacion,
    refrescarConversaciones,
  };
}
