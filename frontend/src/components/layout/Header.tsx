import { MessageSquarePlus, Moon, Sun } from "lucide-react";
import { ASSETS } from "../../core/config";
import { useTheme } from "../../context/ThemeContext";
import type { AppTab } from "./Sidebar";

interface HeaderProps {
  tabActiva: AppTab;
  tituloConversacionActiva?: string | null;
  onNuevaConversacion: () => void;
}

export function Header({
  tabActiva,
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

        {/* Controles derechos: Estado de conexión, Modo Oscuro y Nueva Conversación */}
        <div className="flex items-center gap-2.5">
          {/* Indicador de estado de conexión del prototipo */}
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

          {/* Botón Modo Claro / Modo Oscuro */}
          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated hover:bg-slate-100 dark:hover:bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-200 active:scale-[0.97] transition-all cursor-pointer"
            title={esOscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
            aria-label={esOscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          >
            {esOscuro ? (
              <>
                <Sun className="h-3.5 w-3.5 text-amber-400" />
                <span className="hidden md:inline">Claro</span>
              </>
            ) : (
              <>
                <Moon className="h-3.5 w-3.5 text-slate-600" />
                <span className="hidden md:inline">Oscuro</span>
              </>
            )}
          </button>

          {/* Botón para iniciar una nueva sesión limpia en el Chat */}
          {tabActiva === "chat" && (
            <button
              type="button"
              onClick={onNuevaConversacion}
              title="Iniciar nueva conversación limpia"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated hover:bg-slate-100 dark:hover:bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-200 active:scale-[0.97] transition-all cursor-pointer"
            >
              <MessageSquarePlus className="h-3.5 w-3.5 text-cobalt-600 dark:text-cobalt-400" />
              <span className="hidden sm:inline">Nuevo chat</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
