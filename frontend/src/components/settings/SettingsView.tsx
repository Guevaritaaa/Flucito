import { Cloud, Database, Moon, Sun } from "lucide-react";
import { useTheme } from "../../context/ThemeContext";
import type { UsuarioOut } from "../../schemas/auth";
import { UserManagementSection } from "./UserManagementSection";

interface SettingsViewProps {
  usuario: UsuarioOut;
  esAdmin: boolean;
}

export function SettingsView({ usuario, esAdmin }: SettingsViewProps) {
  const { esOscuro, toggleTheme } = useTheme();

  return (
    <main
      className="min-h-0 min-w-0 flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-6 overflow-y-auto custom-scroll space-y-8 animate-stage-in"
      id="tab-configuracion-content"
    >
      {/* Bloque 1: Preferencias del Sistema en cristal esmerilado */}
      <section className="space-y-4">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Configuración del Sistema
          </h1>
          <p className="text-xs font-medium text-slate-600 dark:text-sky-100/75 mt-0.5">
            Preferencias visuales y estado de conexiones de Flucito AI
          </p>
        </div>

        <div className="rounded-2xl border border-white/85 dark:border-sky-300/20 bg-white/76 dark:bg-[#0a1936]/80 backdrop-blur-xl shadow-[0_12px_32px_rgba(12,50,110,0.08)] dark:shadow-[0_16px_40px_rgba(2,8,26,0.5)] divide-y divide-slate-900/8 dark:divide-sky-200/12">
          {/* Opción 1: Modo Nocturno / Apariencia */}
          <div className="p-4 sm:p-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5">
            <div className="flex min-w-0 flex-[1_0_12rem] items-start gap-3">
              <div className="p-2 rounded-xl bg-[#0022e6]/10 dark:bg-sky-400/15 text-[#0018cc] dark:text-sky-300 mt-0.5">
                {esOscuro ? (
                  <Moon className="h-5 w-5" />
                ) : (
                  <Sun className="h-5 w-5" />
                )}
              </div>
              <div>
                <p className="text-sm font-bold text-slate-900 dark:text-white">
                  Modo oscuro (Descanso visual nocturno)
                </p>
                <p className="text-xs text-slate-600 dark:text-sky-100/75 mt-0.5">
                  Reduce el brillo con superficies de cristal azul profundo para trabajar cómodamente de noche.
                </p>
              </div>
            </div>

            <button
              type="button"
              role="switch"
              aria-label="Modo oscuro"
              aria-checked={esOscuro}
              onClick={toggleTheme}
              className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors cursor-pointer ${
                esOscuro ? "bg-[#1d4ed8]" : "bg-slate-300/90"
              }`}
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-xs transition-transform ${
                  esOscuro ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>

          {/* Opción 2: Integración Google Drive */}
          <div className="p-4 sm:p-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5">
            <div className="flex min-w-0 flex-[1_0_12rem] items-start gap-3">
              <div className="p-2 bg-[#0022e6]/10 dark:bg-sky-400/15 text-[#0018cc] dark:text-sky-300 rounded-xl mt-0.5">
                <Cloud className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-bold text-slate-900 dark:text-white">
                  Almacenamiento en Google Drive
                </p>
                <p className="text-xs text-slate-600 dark:text-sky-100/75 mt-0.5">
                  Lectura directa de facturas en <code className="font-semibold">DOCUMENTOS ENTRADA</code> y guardado de reportes por fecha.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/14 dark:bg-emerald-950/65 text-emerald-900 dark:text-emerald-300 border border-emerald-400/40 dark:border-emerald-500/30">
              Vinculado
            </span>
          </div>

          {/* Opción 3: Base de Datos PostgreSQL y Catálogo SAE */}
          <div className="p-4 sm:p-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5">
            <div className="flex min-w-0 flex-[1_0_12rem] items-start gap-3">
              <div className="p-2 bg-[#0022e6]/10 dark:bg-sky-400/15 text-[#0018cc] dark:text-sky-300 rounded-xl mt-0.5">
                <Database className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-bold text-slate-900 dark:text-white">
                  Catálogo Maestro Aspel SAE (PostgreSQL)
                </p>
                <p className="text-xs text-slate-600 dark:text-sky-100/75 mt-0.5">
                  21,967 artículos, 80 líneas, 512 proveedores y factores de precio sincronizados.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/14 dark:bg-emerald-950/65 text-emerald-900 dark:text-emerald-300 border border-emerald-400/40 dark:border-emerald-500/30">
              Sincronizado
            </span>
          </div>

          {/* Opción 4: Idioma */}
          <div className="p-4 sm:p-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5">
            <div>
              <p className="text-sm font-bold text-slate-900 dark:text-white">
                Idioma del Asistente
              </p>
              <p className="text-xs text-slate-600 dark:text-sky-100/75 mt-0.5">
                Idioma por defecto para respuestas y reportes de almacén.
              </p>
            </div>
            <select
              defaultValue="es-MX"
              aria-label="Idioma del Asistente"
              className="max-w-full rounded-xl border border-white/90 dark:border-sky-300/20 bg-white/90 dark:bg-[#071229]/90 px-3 py-1.5 text-xs font-semibold text-slate-800 dark:text-slate-100 focus:border-[#0022e6] dark:focus:border-sky-400 focus:outline-none"
            >
              <option value="es-MX">Español (Latinoamérica)</option>
              <option value="en-US">English (US)</option>
            </select>
          </div>
        </div>
      </section>

      {/* Bloque 2: Administración de Usuarios (Exclusivo para Administradores) */}
      {esAdmin && <UserManagementSection usuarioActualId={usuario.id} />}
    </main>
  );
}
