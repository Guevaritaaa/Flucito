import { useEffect, useState } from "react";
import { ACCESO_SAE_REQUERIDO } from "../../schemas/chat";
import { ApiError } from "../../services/http";

export function useConsultaSae<Filtro, Datos>(
  inicial: NoInfer<Filtro>,
  consultar: (filtro: Filtro, signal: AbortSignal) => Promise<Datos>,
  revalidarAcceso: (silencioso: boolean) => Promise<void>,
) {
  const [solicitud, setSolicitud] = useState({ filtro: inicial });
  const [resultado, setResultado] = useState<{ datos: Datos; filtro: Filtro } | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCargando(true);
    setError(null);
    consultar(solicitud.filtro, controller.signal).then((datos) => {
      if (!controller.signal.aborted) setResultado({ datos, filtro: solicitud.filtro });
    }).catch((err: unknown) => {
      if (controller.signal.aborted) return;
      if (err instanceof ApiError && (err.isForbidden || err.isUnauthorized)) {
        setResultado(null);
        setError(ACCESO_SAE_REQUERIDO);
        if (err.isForbidden) void revalidarAcceso(true);
      } else {
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el resumen de Aspel SAE.");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setCargando(false);
    });
    return () => controller.abort();
  }, [consultar, revalidarAcceso, solicitud]);

  return { resultado, cargando, error, aplicar: (filtro: Filtro) => setSolicitud({ filtro }), reintentar: () => setSolicitud({ ...solicitud }) };
}
