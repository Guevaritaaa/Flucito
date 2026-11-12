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
      className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-8 overflow-y-auto custom-scroll space-y-8"
      id="tab-configuracion-content"
    >
      {/* Bloque 1: Preferencias del Sistema (del prototipo + Modo Oscuro) */}
      <section className="space-y-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-white">
            Configuración del Sistema
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Preferencias visuales y estado de conexiones de Flucito AI
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-surface shadow-subtle divide-y divide-slate-100 dark:divide-slate-800/80">
          {/* Opción 1: Modo Nocturno / Apariencia */}
          <div className="p-5 flex items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-cobalt-50 dark:bg-cobalt-950/80 text-cobalt-700 dark:text-cobalt-300 mt-0.5">
                {esOscuro ? (
                  <Moon className="h-5 w-5" />
                ) : (
                  <Sun className="h-5 w-5" />
                )}
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  Modo oscuro (Descanso visual nocturno)
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Reduce el brillo con superficies azul cobalto profundo para trabajar cómodamente de noche.
                </p>
              </div>
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={esOscuro}
              onClick={toggleTheme}
              className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors cursor-pointer ${
                esOscuro ? "bg-cobalt-600" : "bg-slate-200"
              }`}
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-xs transition-transform ${
                  esOscuro ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>

          {/* Opción 2: Integración Google Drive (del prototipo) */}
          <div className="p-5 flex items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-blue-50 dark:bg-cobalt-950/80 text-cobalt-700 dark:text-cobalt-300 rounded-lg mt-0.5">
                <Cloud className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  Almacenamiento en Google Drive
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Lectura directa de facturas en <code className="font-semibold">DOCUMENTOS ENTRADA</code> y guardado de reportes por fecha.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60">
              Vinculado
            </span>
          </div>

          {/* Opción 3: Base de Datos PostgreSQL y Catálogo SAE */}
          <div className="p-5 flex items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-blue-50 dark:bg-cobalt-950/80 text-cobalt-700 dark:text-cobalt-300 rounded-lg mt-0.5">
                <Database className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                  Catálogo Maestro Aspel SAE (PostgreSQL)
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  21,967 artículos, 80 líneas, 512 proveedores y factores de precio sincronizados.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60">
              Sincronizado
            </span>
          </div>

          {/* Opción 4: Idioma (del prototipo) */}
          <div className="p-5 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                Idioma del Asistente
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Idioma por defecto para respuestas y reportes de almacén.
              </p>
            </div>
            <select
              defaultValue="es-MX"
              className="rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-dark-canvas px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 focus:border-cobalt-600 focus:outline-none"
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
