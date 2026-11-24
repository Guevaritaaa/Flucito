import type { MensajeUI } from "../../hooks/useChat";

/** Conserva el texto histórico y muestra una sola tarjeta por decisión o reporte. */
export function mensajeVigente(mensaje: MensajeUI, posteriores: MensajeUI[]): MensajeUI {
  const revisionPosterior = mensaje.revision_reporte && posteriores.some(m => m.revision_reporte?.id === mensaje.revision_reporte?.id);
  return { ...mensaje,
    interaccion: mensaje.interaccion && posteriores.some(m => m.interaccion?.id === mensaje.interaccion?.id || m.interaccion?.anteriores?.some(a => a.id === mensaje.interaccion?.id)) ? null : mensaje.interaccion,
    revision_reporte: revisionPosterior ? null : mensaje.revision_reporte,
    avisos: revisionPosterior ? [] : mensaje.avisos,
  };
}
