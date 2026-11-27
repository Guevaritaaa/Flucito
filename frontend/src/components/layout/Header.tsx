import { Moon, PanelLeftOpen, SquarePen, Sun } from "lucide-react";
import { useTheme } from "../../context/ThemeContext";
import type { AppTab } from "./Sidebar";

interface HeaderProps {
  tabActiva: AppTab;
  sidebarAbierto: boolean;
  tituloConversacionActiva?: string | null;
  onToggleSidebar: () => void;
  onNuevaConversacion: () => void;
}

export function Header({
  tabActiva,
  sidebarAbierto,
  tituloConversacionActiva,
  onToggleSidebar,
  onNuevaConversacion,
}: HeaderProps) {
  const { esOscuro, toggleTheme } = useTheme();

  const etiquetaModo = esOscuro ? "Activar modo claro" : "Activar modo oscuro";

  const etiquetas = {
    configuracion: "Configuración • Interflu AI",
    inicio: "Inicio • Interflu AI",
    sae: "Aspel SAE • Interflu AI",
  };
  const etiquetaCentral = tabActiva === "chat"
    ? `Flucito • ${tituloConversacionActiva || "Interflu AI"}`
    : etiquetas[tabActiva];

  return (
    <header
      className="relative z-20 flex h-14 w-full flex-shrink-0 items-center justify-between gap-2 px-2.5 sm:px-6 pt-1"
      data-purpose="app-header"
    >
      {/* Controles izquierdos estilo ChatGPT: visibles en móvil o cuando el sidebar está colapsado */}
      <div className="flex shrink-0 sm:min-w-[76px] items-center gap-1.5">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-label="Mostrar barra lateral"
          aria-controls="sidebar"
          aria-expanded={sidebarAbierto}
          title="Mostrar barra lateral"
          className={`flex h-11 w-11 md:h-9 md:w-9 items-center justify-center rounded-xl border border-white/75 dark:border-sky-300/20 bg-white/60 dark:bg-[#0e2248]/65 backdrop-blur-md text-slate-700 dark:text-slate-100 hover:bg-white/90 dark:hover:bg-[#152f61]/85 active:scale-[0.96] transition-all duration-150 cursor-pointer ${
            sidebarAbierto ? "md:hidden" : ""
          }`}
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>

        {(
          <button
            type="button"
            onClick={onNuevaConversacion}
            aria-label="Nuevo chat"
            title="Nuevo chat"
            className={`flex h-11 w-11 md:h-9 md:w-9 items-center justify-center rounded-xl border border-white/75 dark:border-sky-300/20 bg-white/60 dark:bg-[#0e2248]/65 backdrop-blur-md text-[#0022e6] dark:text-sky-300 hover:bg-white/90 dark:hover:bg-[#152f61]/85 active:scale-[0.96] transition-all duration-150 cursor-pointer ${
              sidebarAbierto ? "md:hidden" : ""
            }`}
          >
            <SquarePen className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Cápsula central de identidad (solo elementos reales, sin desplegables ficticios) */}
      <div className="flex min-w-0 max-w-[55%] items-center justify-center">
        <div
          className="inline-flex max-w-full items-center gap-2 rounded-full border border-white/80 dark:border-sky-300/20 bg-white/68 dark:bg-[#0e2248]/70 backdrop-blur-md px-2.5 sm:px-4 py-1.5 shadow-[0_4px_14px_rgba(12,50,110,0.06)]"
          title={etiquetaCentral}
        >
          <span className="truncate text-xs sm:text-[13px] font-semibold tracking-tight text-slate-800 dark:text-slate-100">
            {etiquetaCentral}
          </span>
        </div>
      </div>

      {/* Controles derechos: Estado Conectado + Modo Claro/Oscuro (mismo estilo que LoginView) */}
      <div className="flex shrink-0 sm:min-w-[76px] items-center justify-end gap-2">
        <div className="group relative">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={etiquetaModo}
            className="flex h-11 w-11 md:h-9 md:w-9 items-center justify-center rounded-xl border border-white/75 dark:border-sky-300/25 bg-white/60 dark:bg-[#0e2248]/65 backdrop-blur-md text-slate-700 dark:text-slate-100 hover:bg-white/90 dark:hover:bg-[#152f61]/85 active:scale-[0.96] transition-all duration-150 cursor-pointer"
          >
            {esOscuro ? (
              <Sun className="h-4 w-4 text-amber-300 transition-transform duration-200 group-hover:rotate-12" />
            ) : (
              <Moon className="h-4 w-4 text-[#0018cc] transition-transform duration-200 group-hover:-rotate-12" />
            )}
          </button>
          <span
            role="tooltip"
            className="pointer-events-none absolute hidden md:block right-0 top-full mt-2 z-50 whitespace-nowrap rounded-lg bg-slate-900/95 border border-white/15 px-2.5 py-1 text-[11px] font-medium text-white shadow-md opacity-0 scale-95 origin-top-right group-hover:opacity-100 group-hover:scale-100 group-focus-within:opacity-100 group-focus-within:scale-100 transition-all duration-150 ease-out"
          >
            {etiquetaModo}
          </span>
        </div>
      </div>
    </header>
  );
}
