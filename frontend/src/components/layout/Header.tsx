import { MessageSquarePlus, Moon, Sun } from "lucide-react";
import { ASSETS } from "../../core/config";
import { useTheme } from "../../context/ThemeContext";
import type { AppTab } from "./Sidebar";

interface HeaderProps {
  tabActiva: AppTab;
  sidebarAbierto: boolean;
  tituloConversacionActiva?: string | null;
  onNuevaConversacion: () => void;
}

export function Header({
  tabActiva,
  sidebarAbierto,
  tituloConversacionActiva,
  onNuevaConversacion,
}: HeaderProps) {
  const { esOscuro, toggleTheme } = useTheme();

  const subtitulo =
    tabActiva === "chat"
      ? tituloConversacionActiva || "Nueva sesión de conversación"
      : tabActiva === "configuracion"
        ? "Preferencias del sistema y administración de cuentas"
        : "Portal de bienvenida y acceso rápido";

  const etiquetaModo = esOscuro ? "Activar modo claro" : "Activar modo oscuro";

  return (
    <header
      className="sticky top-0 z-30 w-full flex-shrink-0 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-surface shadow-2xs transition-colors duration-200"
      data-purpose="app-header"
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Identidad y Branding de Interflu / Flucito */}
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="h-10 w-10 flex-shrink-0 overflow-hidden rounded-xl bg-white shadow-md ring-2 ring-cobalt-100 dark:ring-cobalt-900">
            <img
              src={ASSETS.FLUCITO_AVATAR}
              alt="Flucito"
              width={40}
              height={40}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white leading-tight">
                Flucito
              </h1>
              <span className="inline-flex items-center rounded border border-cobalt-100 dark:border-cobalt-800 bg-cobalt-50 dark:bg-cobalt-950/80 px-2 py-0.5 text-[11px] font-semibold text-cobalt-700 dark:text-cobalt-300">
                Interflu AI
              </span>
            </div>
            <p className="truncate text-xs font-medium text-slate-500 dark:text-slate-400 hidden sm:block">
              {subtitulo}
            </p>
          </div>
        </div>

        {/* Controles derechos minimalistas y sin duplicación */}
        <div className="flex items-center gap-2">
          {/* Indicador de estado de conexión */}
          <div
            className="flex items-center gap-2 rounded-full border border-emerald-200/80 dark:border-emerald-800/60 bg-emerald-50 dark:bg-emerald-950/50 px-3 py-1.5"
            title="Conectado al servidor de Flucito"
          >
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
            <span className="text-xs font-semibold text-emerald-800 dark:text-emerald-300 hidden xs:inline">
              Conectado
            </span>
          </div>

          {/* Botón Nueva Conversación: SOLO aparece en el Header cuando la Sidebar está oculta */}
          {tabActiva === "chat" && !sidebarAbierto && (
            <div className="group relative">
              <button
                type="button"
                onClick={onNuevaConversacion}
                aria-label="Nueva conversación"
                className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated text-cobalt-600 dark:text-cobalt-400 hover:bg-cobalt-50 dark:hover:bg-slate-800 active:scale-[0.96] transition-all duration-150 cursor-pointer"
              >
                <MessageSquarePlus className="h-4 w-4" />
              </button>
              <span
                role="tooltip"
                className="pointer-events-none absolute right-0 top-full mt-2 z-50 whitespace-nowrap rounded-lg bg-slate-900 dark:bg-slate-800 border border-slate-700/80 px-2.5 py-1 text-[11px] font-medium text-white shadow-md opacity-0 scale-95 origin-top-right group-hover:opacity-100 group-hover:scale-100 group-focus-within:opacity-100 group-focus-within:scale-100 transition-all duration-150 ease-out"
              >
                Nueva conversación
              </span>
            </div>
          )}

          {/* Botón de Modo Oscuro / Claro: Solo ícono con tooltip en hover */}
          <div className="group relative">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={etiquetaModo}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated text-slate-600 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-cobalt-700 dark:hover:text-amber-300 active:scale-[0.96] transition-all duration-150 cursor-pointer"
            >
              {esOscuro ? (
                <Sun className="h-4 w-4 text-amber-400 transition-transform duration-200 group-hover:rotate-12" />
              ) : (
                <Moon className="h-4 w-4 text-slate-600 group-hover:text-cobalt-700 transition-transform duration-200 group-hover:-rotate-12" />
              )}
            </button>
            <span
              role="tooltip"
              className="pointer-events-none absolute right-0 top-full mt-2 z-50 whitespace-nowrap rounded-lg bg-slate-900 dark:bg-slate-800 border border-slate-700/80 px-2.5 py-1 text-[11px] font-medium text-white shadow-md opacity-0 scale-95 origin-top-right group-hover:opacity-100 group-hover:scale-100 group-focus-within:opacity-100 group-focus-within:scale-100 transition-all duration-150 ease-out"
            >
              {etiquetaModo}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
