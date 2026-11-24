import { AlertTriangle, CircleAlert } from "lucide-react";
import type { AvisoReporte } from "../../schemas/chat";

export function AvisoEstado({ aviso }: { aviso: AvisoReporte }) {
  const error = aviso.nivel === "error";
  const Icono = error ? CircleAlert : AlertTriangle;
  return <aside role={error ? "alert" : "status"} aria-live="polite" className={`flex min-w-0 gap-3 rounded-xl border p-3 text-sm ${error
    ? "border-red-300 bg-red-50 text-red-950 dark:border-red-700 dark:bg-red-950/50 dark:text-red-100"
    : "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-600 dark:bg-amber-950/50 dark:text-amber-100"}`}>
    <Icono aria-hidden="true" size={19} className="mt-0.5 shrink-0" />
    <div className="min-w-0 space-y-2 break-words"><p className="font-semibold">{aviso.titulo}</p><p className="leading-relaxed">{aviso.descripcion}</p><p className="font-medium">{aviso.accion}</p></div>
  </aside>;
}
