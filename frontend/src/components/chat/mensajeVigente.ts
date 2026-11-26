import type { MensajeUI } from "../../hooks/useChat";

/** Conserva el texto histórico y muestra una sola tarjeta por decisión o reporte. */
export function mensajeVigente(mensaje: MensajeUI, posteriores: MensajeUI[]): MensajeUI {
  const revisionPosterior = mensaje.revision_reporte && posteriores.some(m => m.revision_reporte?.id === mensaje.revision_reporte?.id);
  let interaccion = mensaje.interaccion;
  if (interaccion) {
    const id = interaccion.id;
    if (posteriores.some(m => m.interaccion?.id === id)) {
      interaccion = null;
    } else {
      const posterior = posteriores.find(m => m.interaccion?.anteriores?.some(a => a.id === id));
      interaccion = posterior?.interaccion?.anteriores?.find(a => a.id === id) ?? interaccion;
    }
  }
  return { ...mensaje,
    interaccion,
    revision_reporte: revisionPosterior ? null : mensaje.revision_reporte,
    avisos: revisionPosterior ? [] : mensaje.avisos,
  };
}
