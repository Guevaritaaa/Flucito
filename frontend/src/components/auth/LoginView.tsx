import { useState, type FormEvent } from "react";
import {
  AlertCircle,
  ArrowRight,
  Clock,
  Eye,
  EyeOff,
  Lock,
  Moon,
  Sun,
  User,
} from "lucide-react";
import { ASSETS } from "../../core/config";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { ApiError } from "../../services/http";

export function LoginView() {
  const { login } = useAuth();
  const { esOscuro, toggleTheme } = useTheme();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mostrarPassword, setMostrarPassword] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [esBloqueoTemporal, setEsBloqueoTemporal] = useState(false);

  async function manejarSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const usuarioLimpio = username.trim().toLowerCase();
    if (!usuarioLimpio || !password) {
      setErrorMsg("Ingresa tu usuario y contraseña para continuar.");
      setEsBloqueoTemporal(false);
      return;
    }

    setEnviando(true);
    setErrorMsg(null);
    setEsBloqueoTemporal(false);

    try {
      await login({ username: usuarioLimpio, password });
    } catch (err) {
      if (err instanceof ApiError) {
        setEsBloqueoTemporal(err.isRateLimited);
        setErrorMsg(err.message);
      } else {
        setEsBloqueoTemporal(false);
        setErrorMsg("No fue posible conectar con el servidor de Flucito. Verifica que el backend esté activo.");
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="relative flex min-h-full w-full flex-col justify-center bg-[#f4f6fa] dark:bg-dark-canvas px-4 py-10 sm:px-6 lg:px-8 transition-colors duration-200">
      {/* Botón superior derecho solo ícono con tooltip en hover para Modo Oscuro / Claro */}
      <div className="absolute top-5 right-5 z-20 group">
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={esOscuro ? "Activar modo claro" : "Activar modo oscuro"}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-700/80 bg-white dark:bg-dark-surface text-slate-700 dark:text-slate-200 shadow-subtle hover:bg-slate-50 dark:hover:bg-dark-elevated active:scale-[0.96] transition-all duration-150 cursor-pointer"
        >
          {esOscuro ? (
            <Sun className="h-4 w-4 text-amber-400 transition-transform duration-200 group-hover:rotate-12" />
          ) : (
            <Moon className="h-4 w-4 text-cobalt-700 transition-transform duration-200 group-hover:-rotate-12" />
          )}
        </button>
        <span
          role="tooltip"
          className="pointer-events-none absolute right-0 top-full mt-2 z-50 whitespace-nowrap rounded-lg bg-slate-900 dark:bg-slate-800 border border-slate-700/80 px-2.5 py-1 text-[11px] font-medium text-white shadow-md opacity-0 scale-95 origin-top-right group-hover:opacity-100 group-hover:scale-100 group-focus-within:opacity-100 group-focus-within:scale-100 transition-all duration-150 ease-out"
        >
          {esOscuro ? "Activar modo claro" : "Activar modo oscuro"}
        </span>
      </div>

      <div className="mx-auto w-full max-w-md">
        {/* Tarjeta principal con la paleta exacta del prototipo */}
        <div className="overflow-hidden rounded-3xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-dark-surface shadow-elevation transition-colors duration-200">
          {/* Cabecera Azul Cobalto (#0018CC) idéntica al Sidebar del prototipo */}
          <div className="bg-[#0018CC] dark:bg-dark-sidebar border-b border-[#0014a8] dark:border-cobalt-900/80 px-7 py-6 text-white">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3.5">
                <div className="h-12 w-12 flex-shrink-0 overflow-hidden rounded-xl bg-white ring-2 ring-white/30 shadow-md">
                  <img
                    src={ASSETS.FLUCITO_AVATAR}
                    alt="Flucito"
                    width={48}
                    height={48}
                    className="h-full w-full object-cover"
                  />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h1 className="text-xl font-bold tracking-tight text-white">Flucito</h1>
                    <span className="inline-flex items-center rounded bg-white/15 border border-white/25 px-2 py-0.5 text-[11px] font-semibold text-blue-50">
                      Interflu AI
                    </span>
                  </div>
                  <p className="text-xs text-blue-100/90 font-medium mt-0.5">
                    Portal de Almacén y Asistente Virtual
                  </p>
                </div>
              </div>

              <div className="hidden sm:flex items-center justify-center rounded-lg border border-white/30 bg-white/10 px-2.5 py-1.5 backdrop-blur-xs">
                <img
                  src={ASSETS.INTERFLU_LOGO}
                  alt="Interflu"
                  className="h-7 w-auto object-contain"
                />
              </div>
            </div>
          </div>

          {/* Cuerpo del formulario */}
          <div className="p-7 sm:p-8 space-y-6">
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                Iniciar sesión
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Ingresa con tu cuenta de operador o administrador para acceder a tus conversaciones y reportes.
              </p>
            </div>

            {errorMsg && (
              <div
                role="alert"
                className={`flex items-start gap-2.5 rounded-xl border p-3.5 text-xs leading-relaxed ${
                  esBloqueoTemporal
                    ? "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-200"
                    : "border-red-200 bg-red-50 text-red-800 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-200"
                }`}
              >
                {esBloqueoTemporal ? (
                  <Clock className="h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
                ) : (
                  <AlertCircle className="h-4 w-4 flex-shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
                )}
                <span className="font-medium">{errorMsg}</span>
              </div>
            )}

            <form onSubmit={manejarSubmit} className="space-y-4" noValidate>
              {/* Campo Usuario */}
              <div className="space-y-1.5">
                <label
                  htmlFor="login-username"
                  className="block text-xs font-semibold text-slate-700 dark:text-slate-300"
                >
                  Usuario
                </label>
                <div className="relative">
                  <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400 dark:text-slate-500">
                    <User className="h-4 w-4" />
                  </span>
                  <input
                    id="login-username"
                    name="username"
                    type="text"
                    autoComplete="username"
                    autoFocus
                    required
                    disabled={enviando}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Ej. robert u operador"
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-[#f8fafc] dark:bg-dark-canvas py-2.5 pl-10 pr-3.5 text-sm text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 transition-colors focus:border-cobalt-600 dark:focus:border-cobalt-400 focus:bg-white dark:focus:bg-dark-surface focus:outline-none disabled:opacity-60"
                  />
                </div>
              </div>

              {/* Campo Contraseña */}
              <div className="space-y-1.5">
                <label
                  htmlFor="login-password"
                  className="block text-xs font-semibold text-slate-700 dark:text-slate-300"
                >
                  Contraseña
                </label>
                <div className="relative">
                  <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400 dark:text-slate-500">
                    <Lock className="h-4 w-4" />
                  </span>
                  <input
                    id="login-password"
                    name="password"
                    type={mostrarPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    disabled={enviando}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Ingresa tu contraseña"
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-[#f8fafc] dark:bg-dark-canvas py-2.5 pl-10 pr-10 text-sm text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 transition-colors focus:border-cobalt-600 dark:focus:border-cobalt-400 focus:bg-white dark:focus:bg-dark-surface focus:outline-none disabled:opacity-60"
                  />
                  <button
                    type="button"
                    onClick={() => setMostrarPassword((prev) => !prev)}
                    tabIndex={-1}
                    aria-label={mostrarPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                  >
                    {mostrarPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              {/* Botón de envío con el azul cobalto del prototipo (bg-cobalt-600 hover:bg-cobalt-700) */}
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={enviando}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-cobalt-600 hover:bg-cobalt-700 active:scale-[0.98] px-5 py-3 text-sm font-semibold text-white shadow-md hover:shadow-lg transition-all disabled:opacity-60 disabled:pointer-events-none cursor-pointer"
                >
                  {enviando ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                      <span>Verificando acceso...</span>
                    </>
                  ) : (
                    <>
                      <span>Entrar a Flucito</span>
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Pie discreto */}
        <p className="mt-5 text-center text-[11px] text-slate-400 dark:text-slate-500">
          Flucito AI • Sistema Interno de Almacén Interflu
        </p>
      </div>
    </div>
  );
}
