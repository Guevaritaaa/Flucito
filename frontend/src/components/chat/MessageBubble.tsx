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
        <div className="max-w-[85%] sm:max-w-xl rounded-2xl rounded-tr-sm bg-[#0022e6] dark:bg-[#1d4ed8] px-4 py-3 text-white shadow-[0_8px_22px_rgba(0,34,230,0.22)] dark:shadow-[0_8px_24px_rgba(29,78,216,0.38)]">
          <p className="whitespace-pre-wrap break-words text-sm sm:text-[15px] font-normal leading-relaxed">
            {mensaje.contenido}
          </p>
        </div>
        <span className="mt-1 mr-1 text-[11px] font-medium text-slate-600 dark:text-sky-200/65">
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
        {/* Avatar de Flucito 3D coherente con LoginView y Hero */}
        <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/90 dark:border-sky-300/30 bg-gradient-to-b from-sky-100 to-white dark:from-[#163870] dark:to-[#0a1936] shadow-[0_4px_12px_rgba(12,50,110,0.1)]">
          <img
            src={ASSETS.FLUCITO_3D}
            alt="Flucito"
            width={36}
            height={36}
            className="h-full w-full object-cover object-top scale-[1.22] translate-y-0.5 select-none"
          />
        </div>

        {/* Tarjeta de respuesta en cristal esmerilado de alta legibilidad */}
        <div
          className={`max-w-[calc(100%-3rem)] sm:max-w-2xl rounded-2xl rounded-tl-sm px-5 py-4 space-y-3.5 backdrop-blur-xl ${
            mensaje.esError
              ? "border border-red-300/90 dark:border-red-700/50 bg-red-50/90 dark:bg-red-950/65 text-red-900 dark:text-red-200"
              : "border border-white/85 dark:border-sky-200/18 bg-white/78 dark:bg-[#0a1936]/82 text-slate-800 dark:text-slate-100 shadow-[0_10px_28px_rgba(12,50,110,0.07)] dark:shadow-[0_14px_34px_rgba(2,8,26,0.45)]"
          }`}
        >
          <div
            className={`text-sm sm:text-[15px] font-normal leading-relaxed ${
              mensaje.esError
                ? "text-red-800 dark:text-red-200"
                : "text-slate-800 dark:text-slate-100"
            }`}
          >
            <p className="whitespace-pre-wrap break-words">{mensaje.contenido}</p>
          </div>

          {/* Botones reales de descarga de archivos generados (Excel, TXT Aspel, Históricos) */}
          {tieneAdjuntos && (
            <div className="flex flex-wrap items-center gap-2 pt-2.5 border-t border-slate-900/10 dark:border-sky-200/15">
              {mensaje.archivo_almacen_url && (
                <a
                  href={resolverUrlDescarga(mensaje.archivo_almacen_url)}
                  download="BASE_ENTRADAS_ALMACEN.xlsx"
                  className="inline-flex items-center gap-1.5 rounded-xl bg-[#0022e6]/10 hover:bg-[#0022e6]/18 dark:bg-sky-400/15 dark:hover:bg-sky-400/25 px-3.5 py-2 text-xs font-semibold text-[#0018cc] dark:text-sky-200 active:scale-[0.98] transition-all"
                >
                  <FileSpreadsheet className="h-4 w-4 text-[#0022e6] dark:text-sky-300 flex-shrink-0" />
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
                  className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/14 hover:bg-emerald-500/22 dark:bg-emerald-400/15 dark:hover:bg-emerald-400/25 px-3.5 py-2 text-xs font-semibold text-emerald-900 dark:text-emerald-200 active:scale-[0.98] transition-all"
                >
                  <FileText className="h-4 w-4 text-emerald-700 dark:text-emerald-300 flex-shrink-0" />
                  <span>Descargar TXT para Aspel</span>
                </a>
              )}

              {mensaje.reportes_historicos?.map((reporte, idx) => (
                <a
                  key={`${reporte.url}-${idx}`}
                  href={resolverUrlDescarga(reporte.url)}
                  download={reporte.nombre}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-[#0022e6]/10 hover:bg-[#0022e6]/18 dark:bg-sky-400/15 dark:hover:bg-sky-400/25 px-3.5 py-2 text-xs font-semibold text-[#0018cc] dark:text-sky-200 active:scale-[0.98] transition-all"
                >
                  <Download className="h-3.5 w-3.5 text-[#0022e6] dark:text-sky-300 flex-shrink-0" />
                  <span>Descargar {reporte.nombre}</span>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="pl-12 mt-1">
        <span className="text-[11px] font-medium text-slate-600 dark:text-sky-200/65">
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
      <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/90 dark:border-sky-300/30 bg-gradient-to-b from-sky-100 to-white dark:from-[#163870] dark:to-[#0a1936] shadow-[0_4px_12px_rgba(12,50,110,0.1)]">
        <img
          src={ASSETS.FLUCITO_3D}
          alt="Flucito"
          width={36}
          height={36}
          className="h-full w-full object-cover object-top scale-[1.22] translate-y-0.5 select-none"
        />
      </div>

      <div className="flex items-center gap-3 rounded-2xl rounded-tl-sm border border-white/85 dark:border-sky-200/18 bg-white/78 dark:bg-[#0a1936]/82 backdrop-blur-xl px-4 py-3 shadow-[0_8px_24px_rgba(12,50,110,0.06)]">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
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
