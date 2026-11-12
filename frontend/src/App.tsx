import { CheckCircle2, LogOut, Moon, Shield, Sun, UserCheck } from "lucide-react";
import { LoginView } from "./components/auth/LoginView";
import { ASSETS } from "./core/config";
import { useAuth } from "./context/AuthContext";
import { useTheme } from "./context/ThemeContext";

export default function App() {
  const { autenticado, usuario, esAdmin, cargandoSesion, logout } = useAuth();
  const { esOscuro, toggleTheme } = useTheme();

  if (cargandoSesion) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[#f4f6fa] dark:bg-dark-canvas text-slate-700 dark:text-slate-200 transition-colors">
        <div className="flex items-center gap-3 rounded-2xl border border-cobalt-100 dark:border-slate-800 bg-white dark:bg-dark-surface px-5 py-3.5 shadow-subtle">
          <div className="h-8 w-8 overflow-hidden rounded-full ring-2 ring-cobalt-100 bg-white">
            <img
              src={ASSETS.FLUCITO_AVATAR}
              alt="Flucito"
              className="h-full w-full object-cover"
            />
          </div>
          <span className="text-sm font-medium text-cobalt-800 dark:text-slate-200">
            Verificando sesión...
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

  if (!autenticado || !usuario) {
    return <LoginView />;
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-[#f4f6fa] dark:bg-dark-canvas p-6 text-slate-800 dark:text-slate-100 transition-colors duration-200">
      <div className="w-full max-w-lg overflow-hidden rounded-3xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-dark-surface shadow-elevation">
        <div className="bg-[#0018CC] dark:bg-dark-sidebar border-b border-[#0014a8] dark:border-cobalt-900/80 px-7 py-5 text-white flex items-center justify-between">
          <div className="flex items-center gap-3.5">
            <div className="h-11 w-11 overflow-hidden rounded-xl bg-white ring-2 ring-white/30 shadow-md">
              <img
                src={ASSETS.FLUCITO_AVATAR}
                alt="Flucito"
                className="h-full w-full object-cover"
              />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">
                ¡Hola, {usuario.nombre_completo}!
              </h1>
              <p className="text-xs text-blue-100">
                Sesión autenticada correctamente en Flucito AI
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={toggleTheme}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/25 bg-white/10 hover:bg-white/20 px-3 py-1.5 text-xs font-medium text-white transition-colors cursor-pointer"
            title={esOscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          >
            {esOscuro ? (
              <>
                <Sun className="h-3.5 w-3.5 text-amber-300" />
                <span>Claro</span>
              </>
            ) : (
              <>
                <Moon className="h-3.5 w-3.5 text-blue-100" />
                <span>Oscuro</span>
              </>
            )}
          </button>
        </div>

        <div className="p-7 space-y-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200/80 dark:border-slate-700/70 bg-slate-50/80 dark:bg-dark-canvas p-4 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-cobalt-700 dark:text-cobalt-300">
                <UserCheck className="h-4 w-4" />
                <span>Usuario Activo</span>
              </div>
              <p className="text-sm font-bold text-slate-900 dark:text-white">
                @{usuario.username}
              </p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                {usuario.nombre_completo}
              </p>
            </div>

            <div className="rounded-xl border border-slate-200/80 dark:border-slate-700/70 bg-slate-50/80 dark:bg-dark-canvas p-4 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-cobalt-700 dark:text-cobalt-300">
                <Shield className="h-4 w-4" />
                <span>Rol de Acceso</span>
              </div>
              <p className="text-sm font-bold text-slate-900 dark:text-white capitalize">
                {esAdmin ? "Administrador" : "Operador de Almacén"}
              </p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Token JWT verificado con PostgreSQL
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-xl border border-emerald-200/80 dark:border-emerald-800/50 bg-emerald-50/80 dark:bg-emerald-950/30 px-4 py-3 text-xs text-emerald-800 dark:text-emerald-200">
            <span className="flex items-center gap-2 font-medium">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              Fase 3 lista • Siguiente paso: Sidebar e Historial de Conversaciones (Fase 4)
            </span>
          </div>

          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 active:scale-[0.98] transition-all cursor-pointer"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Cerrar sesión</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
