import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { ASSETS } from "../../core/config";
import type { MensajeUI } from "../../hooks/useChat";
import { resolverUrlDescarga } from "../../services/almacenService";

interface MessageBubbleProps {
  mensaje: MensajeUI;
}

export function MessageBubble({ mensaje }: MessageBubbleProps) {
  if (mensaje.rol === "user") {
    return (
      <div className="flex flex-col items-end" data-role="user-message">
        <div className="max-w-xl rounded-2xl rounded-tr-sm border border-slate-200/80 dark:border-slate-700/80 bg-white dark:bg-dark-surface px-4 py-3.5 shadow-subtle">
          <p className="whitespace-pre-wrap text-sm font-normal leading-relaxed text-slate-800 dark:text-slate-100">
            {mensaje.contenido}
          </p>
        </div>
        <span className="mt-1 mr-1 text-[11px] text-slate-400 dark:text-slate-500">
          {mensaje.hora}
        </span>
      </div>
    );
  }

  const tieneAdjuntos =
    Boolean(mensaje.archivo_almacen_url) ||
    Boolean(mensaje.archivo_txt_url) ||
    Boolean(mensaje.reportes_historicos && mensaje.reportes_historicos.length > 0);

  const esTxtTabs = Boolean(
    mensaje.archivo_txt_url && mensaje.archivo_txt_url.includes("tabs")
  );

  return (
    <div className="flex flex-col items-start" data-role="assistant-message">
      <div className="flex items-start gap-3 max-w-full">
        {/* Avatar Flucito */}
        <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-white shadow-sm ring-2 ring-cobalt-100 dark:ring-cobalt-900">
          <img
            src={ASSETS.FLUCITO_AVATAR}
            alt="Flucito"
            width={32}
            height={32}
            className="h-full w-full object-cover"
          />
        </div>

        {/* Burbuja Azul Cobalto del prototipo (#0018cc) */}
        <div
          className={`max-w-2xl rounded-2xl rounded-tl-sm p-5 shadow-elevation space-y-3.5 ${
            mensaje.esError
              ? "border border-red-300 dark:border-red-800/70 bg-red-50 dark:bg-red-950/50 text-red-900 dark:text-red-200"
              : "bg-cobalt-700 dark:bg-cobalt-800 text-white"
          }`}
        >
          <div
            className={`text-sm font-normal leading-relaxed ${
              mensaje.esError
                ? "text-red-800 dark:text-red-200"
                : "text-blue-50"
            }`}
          >
            <p className="whitespace-pre-wrap break-words">{mensaje.contenido}</p>
          </div>

          {/* Botones de descarga de archivos generados (Excel, TXT Aspel, Históricos) */}
          {tieneAdjuntos && (
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-white/15">
              {mensaje.archivo_almacen_url && (
                <a
                  href={resolverUrlDescarga(mensaje.archivo_almacen_url)}
                  download="BASE_ENTRADAS_ALMACEN.xlsx"
                  className="inline-flex items-center gap-1.5 rounded-xl bg-blue-100 hover:bg-white px-3.5 py-2 text-xs font-semibold text-cobalt-800 hover:text-cobalt-900 shadow-xs active:scale-[0.98] transition-all"
                >
                  <FileSpreadsheet className="h-4 w-4 text-cobalt-700 flex-shrink-0" />
                  <span>Descargar Excel de almacén</span>
                </a>
              )}

              {mensaje.archivo_txt_url && (
                <a
                  href={resolverUrlDescarga(mensaje.archivo_txt_url)}
                  download={
                    esTxtTabs
                      ? "BASE_ENTRADAS_ALMACEN_TABS.txt"
                      : "BASE_ENTRADAS_ALMACEN_COMAS.txt"
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-100 hover:bg-emerald-50 px-3.5 py-2 text-xs font-semibold text-emerald-900 shadow-xs active:scale-[0.98] transition-all"
                >
                  <FileText className="h-4 w-4 text-emerald-700 flex-shrink-0" />
                  <span>Descargar TXT para Aspel</span>
                </a>
              )}

              {mensaje.reportes_historicos?.map((reporte, idx) => (
                <a
                  key={`${reporte.url}-${idx}`}
                  href={resolverUrlDescarga(reporte.url)}
                  download={reporte.nombre}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-blue-100 hover:bg-white px-3.5 py-2 text-xs font-semibold text-cobalt-800 hover:text-cobalt-900 shadow-xs active:scale-[0.98] transition-all"
                >
                  <Download className="h-3.5 w-3.5 text-cobalt-700 flex-shrink-0" />
                  <span>Descargar {reporte.nombre}</span>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="pl-11 mt-1">
        <span className="text-[11px] text-slate-400 dark:text-slate-500">
          {mensaje.hora} • Flucito
        </span>
      </div>
    </div>
  );
}

export function FlucitoLoadingBubble() {
  return (
    <div
      className="flex items-start gap-3"
      data-role="assistant-message"
      role="status"
      aria-live="polite"
    >
      <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-white shadow-sm ring-2 ring-cobalt-100 dark:ring-cobalt-900">
        <img
          src={ASSETS.FLUCITO_AVATAR}
          alt="Flucito"
          width={32}
          height={32}
          className="h-full w-full object-cover"
        />
      </div>

      <div className="flex items-center gap-3 rounded-2xl rounded-tl-sm border border-cobalt-100 dark:border-slate-700 bg-white dark:bg-dark-surface px-4 py-3 shadow-subtle">
        <span className="text-sm font-medium text-cobalt-800 dark:text-slate-200">
          Trabajando...
        </span>
        <span className="flex items-center gap-1" aria-hidden="true">
          <span className="trabajando-punto" />
          <span className="trabajando-punto" />
          <span className="trabajando-punto" />
        </span>
      </div>
    </div>
  );
}
