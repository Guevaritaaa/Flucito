import { Check, ChevronDown, CircleAlert, Clock, LoaderCircle } from "lucide-react";
import type { ActividadChat } from "../../schemas/chat";

const estados: Record<string, string> = {
  en_curso: "En curso", completado: "Completado", error: "Interrumpido",
  reintentando: "Reintentando", recuperado: "Recuperado tras un reintento",
  parcial: "Parcial: quedan pasos pendientes", pendiente_verificar: "Pendiente de verificar",
};

export function ActividadDesplegable({ actividades, enCurso = false }: {
  actividades: ActividadChat[]; etapa?: "pensando" | "trabajando"; enCurso?: boolean;
}) {
  // Los snapshots reemplazan el estado completo; no se anexan eventos al reconectar.
  const pasos = actividades.filter((a, i) => !a.id || actividades.findIndex((b) => b.id === a.id) === i);
  const actual = [...pasos].reverse().find((a) => a.estado === "en_curso" || a.estado === "reintentando");
  const pendientes = pasos.some((a) => a.estado === "parcial" || a.estado === "pendiente_verificar");
  const error = pasos.some((a) => a.estado === "error");
  const titulo = enCurso ? actual?.texto ?? "Preparando la solicitud" : pendientes ? "Actividad con pasos pendientes" : error ? "Actividad interrumpida" : "Actividad de Flucito";
  return (
    <details className="group min-w-0 text-sm text-slate-700 dark:text-sky-100" data-testid="actividad">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-md font-semibold focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-blue-600 [&::-webkit-details-marker]:hidden">
        {enCurso ? <LoaderCircle aria-hidden="true" className="h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none" /> : pendientes || error ? <CircleAlert aria-hidden="true" className="h-4 w-4 shrink-0" /> : <Check aria-hidden="true" className="h-4 w-4 shrink-0" />}
        <span className="min-w-0 break-words">{titulo}</span>
        <ChevronDown aria-hidden="true" className="ml-auto h-4 w-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" />
      </summary>
      <div className="mt-3 border-t border-slate-900/10 pt-3 dark:border-sky-200/15">
        <p className="mb-3 text-xs text-slate-600 dark:text-sky-100">Acciones observadas durante la solicitud</p>
        <ol className="space-y-4" aria-label="Pasos de la actividad">
          {pasos.map((a, i) => {
            const activo = a.estado === "en_curso" || a.estado === "reintentando";
            const incompleto = a.estado === "parcial" || a.estado === "pendiente_verificar";
            return <li key={a.id ?? i} className="flex min-w-0 gap-3">
              <span aria-hidden="true" className="mt-0.5 shrink-0">
                {activo ? <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" /> : a.estado === "error" ? <CircleAlert className="h-4 w-4 text-red-700 dark:text-red-300" /> : incompleto ? <Clock className="h-4 w-4 text-amber-800 dark:text-amber-200" /> : <Check className="h-4 w-4 text-emerald-700 dark:text-emerald-300" />}
              </span>
              <div className="min-w-0 flex-1 text-xs leading-relaxed">
                <p className="break-words font-semibold text-slate-800 dark:text-slate-100">{a.texto}</p>
                <p className="mt-0.5 text-slate-600 dark:text-sky-100">{estados[a.estado] ?? "Estado no disponible"}</p>
                {a.resumen && <div className="mt-2">
                  <p className="font-semibold text-slate-800 dark:text-slate-100">Resumen del modelo</p>
                  {a.resumen_idioma === "groq" && <p className="mt-1 text-slate-600 dark:text-sky-100">Traducido automáticamente con Groq</p>}
                  {a.resumen_idioma === "original" && <p className="mt-1 text-slate-600 dark:text-sky-100">Texto original del proveedor</p>}
                  <p className="mt-1 whitespace-pre-wrap break-words text-slate-700 dark:text-sky-100">{a.resumen}</p>
                </div>}
              </div>
            </li>;
          })}
        </ol>
        {!pasos.length && <p className="text-xs">Todavía no hay acciones registradas.</p>}
      </div>
    </details>
  );
}
