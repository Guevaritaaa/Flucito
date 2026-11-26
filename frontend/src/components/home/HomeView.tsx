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
  onNuevaConversacion: () => void;
}

export function HomeView({ usuario, onSelectTab, onNuevaConversacion }: HomeViewProps) {
  return (
    <main
      className="flex min-h-0 flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-8 flex-col items-center overflow-y-auto custom-scroll"
      id="tab-inicio-content"
    >
      <div className="my-auto flex w-full max-w-2xl shrink-0 flex-col gap-4 sm:gap-7 text-center animate-stage-in">
        {/* Retrato central de Flucito 3D en armonía con Login y Chat */}
        <div className="relative mx-auto flex h-18 w-18 sm:h-24 sm:w-24 items-center justify-center">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -inset-2.5 rounded-full bg-cyan-300/40 dark:bg-sky-400/25 blur-xl"
          />
          <div className="relative flex h-18 w-18 sm:h-24 sm:w-24 items-center justify-center overflow-hidden rounded-full border-2 border-white/90 dark:border-sky-300/35 bg-gradient-to-b from-sky-100/90 via-white/80 to-cyan-100/85 dark:from-[#163870] dark:via-[#0e244d] dark:to-[#0a1936] shadow-[0_14px_34px_rgba(14,90,170,0.18)]">
            <img
              src={ASSETS.FLUCITO_3D}
              alt="Flucito"
              width={96}
              height={96}
              className="h-full w-full object-cover object-top scale-[1.22] translate-y-1.5 select-none pointer-events-none"
            />
          </div>
        </div>

        <div className="space-y-2">
          <h1 className="text-xl sm:text-3xl wrap-anywhere font-extrabold tracking-tight text-slate-900 dark:text-white">
            ¡Bienvenido, {usuario.nombre_completo}!
          </h1>
          <p className="mx-auto max-w-lg text-sm sm:text-[15px] leading-relaxed text-slate-700 dark:text-sky-100/85">
            Soy Flucito, el asistente de Interflu. Inicia una nueva conversación para generar reportes a partir de los documentos en Drive, consultar el catálogo de Aspel SAE o descargar reportes anteriores.
          </p>
        </div>

        {/* Acciones principales */}
        <div className="md:order-1 flex flex-wrap items-center justify-center gap-2.5 sm:gap-3 sm:pt-1">
          <button
            type="button"
            onClick={onNuevaConversacion}
            className="inline-flex min-h-11 max-w-full items-center justify-center gap-2 rounded-xl bg-[#0022e6] hover:bg-[#0018cc] dark:bg-[#1d4ed8] dark:hover:bg-[#2563eb] active:scale-[0.98] px-6 py-3 text-sm font-semibold text-white shadow-[0_6px_20px_rgba(0,34,230,0.32)] dark:shadow-[0_6px_22px_rgba(29,78,216,0.45)] transition-all cursor-pointer"
          >
            <MessageSquare className="h-4 w-4" />
            <span>Nueva conversación</span>
            <ArrowRight className="h-4 w-4" />
          </button>

          {usuario.rol === "admin" && (
            <button
              type="button"
              onClick={() => onSelectTab("configuracion")}
              className="inline-flex min-h-11 max-w-full items-center justify-center gap-2 rounded-xl border border-white/85 dark:border-sky-300/22 bg-white/75 dark:bg-[#0e2248]/75 hover:bg-white dark:hover:bg-[#152f61]/90 backdrop-blur-md active:scale-[0.98] px-5 py-3 text-sm font-semibold text-slate-800 dark:text-slate-100 transition-all cursor-pointer"
            >
              <Shield className="h-4 w-4 text-[#0022e6] dark:text-sky-300" />
              <span>Administrar Usuarios</span>
            </button>
          )}
        </div>

        {/* Panel unificado de estado de conexiones en cristal esmerilado (sin tarjetas anidadas) */}
        <div className="rounded-2xl border border-white/85 dark:border-sky-300/20 bg-white/75 dark:bg-[#0a1936]/80 backdrop-blur-xl divide-y sm:divide-y-0 sm:divide-x divide-slate-900/8 dark:divide-sky-200/12 grid grid-cols-1 sm:grid-cols-3 text-left shadow-[0_12px_32px_rgba(12,50,110,0.08)] dark:shadow-[0_16px_40px_rgba(2,8,26,0.5)]">
          <div className="p-4 sm:p-5 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-bold text-[#0018cc] dark:text-sky-300">
              <Database className="h-4 w-4 flex-shrink-0" />
              <span>Catálogo Aspel SAE</span>
            </div>
            <p className="text-xs leading-relaxed text-slate-600 dark:text-sky-100/75">
              Consulta artículos, líneas y proveedores del catálogo de Aspel SAE.
            </p>
          </div>

          <div className="p-4 sm:p-5 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-bold text-[#0018cc] dark:text-sky-300">
              <FolderSync className="h-4 w-4 flex-shrink-0" />
              <span>Flujo en Drive</span>
            </div>
            <p className="text-xs leading-relaxed text-slate-600 dark:text-sky-100/75">
              Consulta los documentos de entrada en Drive y organízalos por fecha.
            </p>
          </div>

          <div className="p-4 sm:p-5 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-bold text-emerald-800 dark:text-emerald-300">
              <FileSpreadsheet className="h-4 w-4 flex-shrink-0" />
              <span>Reportes de entradas</span>
            </div>
            <p className="text-xs leading-relaxed text-slate-600 dark:text-sky-100/75">
              Genera reportes de almacén con precios calculados y descárgalos para SAE.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
