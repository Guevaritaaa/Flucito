import { useId, useState, type ReactNode } from "react";
import { ACCESO_SAE_REQUERIDO } from "../../schemas/chat";

export function AccionSae({ children, permitido, ocupado, paginaActual, onClick, className }: {
  children: ReactNode;
  permitido: boolean;
  ocupado?: boolean;
  paginaActual?: boolean;
  onClick: () => void;
  className?: string;
}) {
  const avisoId = useId();
  const [mostrarAviso, setMostrarAviso] = useState(false);
  return (
    <div className="group/sae relative">
      <button
        type="button"
        aria-disabled={!permitido || ocupado || undefined}
        aria-current={paginaActual ? "page" : undefined}
        aria-describedby={permitido ? undefined : avisoId}
        onClick={() => permitido ? !ocupado && onClick() : setMostrarAviso(true)}
        onBlur={() => setMostrarAviso(false)}
        className={`${className ?? ""} ${permitido ? "cursor-pointer" : "cursor-not-allowed text-slate-600 dark:text-slate-400"}`}
      >
        {children}
      </button>
      {!permitido && (
        <span id={avisoId} role="tooltip" className={`${mostrarAviso ? "visible" : "invisible group-hover/sae:visible group-focus-within/sae:visible"} pointer-events-none absolute top-full left-0 z-20 mt-1 w-max max-w-52 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-800 shadow-md dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100`}>
          {ACCESO_SAE_REQUERIDO}
        </span>
      )}
    </div>
  );
}
