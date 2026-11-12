import {
  ArrowRight,
  Database,
  FileSpreadsheet,
  FolderSync,
  MessageSquare,
  Shield,
} from "lucide-react";
import { ASSETS } from "../../core/config";
import type { UsuarioOut } from "../../schemas/auth";
import type { AppTab } from "../layout/Sidebar";

interface HomeViewProps {
  usuario: UsuarioOut;
  onSelectTab: (tab: AppTab) => void;
  onIniciarConPrompt?: (prompt: string) => void;
}

export function HomeView({ usuario, onSelectTab }: HomeViewProps) {
  return (
    <main
      className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-10 flex flex-col items-center justify-center overflow-y-auto custom-scroll"
      id="tab-inicio-content"
    >
      <div className="w-full max-w-2xl rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-surface p-8 sm:p-10 shadow-elevation space-y-7 text-center transition-colors duration-200">
        {/* Avatar central de Flucito como en el prototipo */}
        <div className="mx-auto flex h-20 w-20 items-center justify-center overflow-hidden rounded-2xl bg-white shadow-lg ring-4 ring-cobalt-100 dark:ring-cobalt-900">
          <img
            src={ASSETS.FLUCITO_AVATAR}
            alt="Flucito"
            width={80}
            height={80}
            className="h-full w-full object-cover"
          />
        </div>

        <div className="space-y-2.5">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            ¡Bienvenido, {usuario.nombre_completo}!
          </h2>
          <p className="mx-auto max-w-lg text-sm leading-relaxed text-slate-600 dark:text-slate-300">
            ¡Hola! Soy Flucito, tu asistente virtual en Interflu. Ve a la pestaña de{" "}
            <strong className="font-semibold text-cobalt-700 dark:text-cobalt-300">
              Chat
            </strong>{" "}
            para procesar facturas de entrada, consultar el catálogo de Aspel SAE o descargar tus reportes de almacén.
          </p>
        </div>

        {/* Resumen rápido de capacidades conectadas */}
        <div className="grid grid-cols-1 gap-3 text-left sm:grid-cols-3">
          <div className="rounded-2xl border border-slate-200/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-dark-canvas p-4 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-cobalt-700 dark:text-cobalt-300">
              <Database className="h-4 w-4 flex-shrink-0" />
              <span>Catálogo Aspel SAE</span>
            </div>
            <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
              21,967 artículos, 80 líneas y 512 proveedores sincronizados en PostgreSQL.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-dark-canvas p-4 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-cobalt-700 dark:text-cobalt-300">
              <FolderSync className="h-4 w-4 flex-shrink-0" />
              <span>Flujo en Drive</span>
            </div>
            <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
              Lectura directa de <code className="font-semibold">DOCUMENTOS ENTRADA</code> y organización por fecha.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-dark-canvas p-4 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
              <FileSpreadsheet className="h-4 w-4 flex-shrink-0" />
              <span>Excel y TXT SAE</span>
            </div>
            <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
              Cálculo automático de los 5 precios por línea y exportación lista para SAE.
            </p>
          </div>
        </div>

        {/* Botones de acción */}
        <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
          <button
            type="button"
            onClick={() => onSelectTab("chat")}
            className="inline-flex items-center gap-2 rounded-xl bg-cobalt-600 hover:bg-cobalt-700 active:scale-[0.97] px-6 py-3 text-sm font-semibold text-white shadow-md hover:shadow-lg transition-all cursor-pointer"
          >
            <MessageSquare className="h-4 w-4" />
            <span>Ir al Chat</span>
            <ArrowRight className="h-4 w-4" />
          </button>

          {usuario.rol === "admin" && (
            <button
              type="button"
              onClick={() => onSelectTab("configuracion")}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated hover:bg-slate-50 dark:hover:bg-slate-800 active:scale-[0.97] px-5 py-3 text-sm font-semibold text-slate-700 dark:text-slate-200 transition-all cursor-pointer"
            >
              <Shield className="h-4 w-4 text-cobalt-600 dark:text-cobalt-400" />
              <span>Administrar Usuarios</span>
            </button>
          )}
        </div>
      </div>
    </main>
  );
}
