import { CheckCircle2, Layers, ShieldCheck, Sparkles } from "lucide-react";
import { API_V1_PREFIX } from "./core/config";

export default function App() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-canvas p-6 text-slate-800">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200/80 bg-surface p-8 shadow-elevation space-y-6">
        <div className="flex items-center justify-between border-b border-slate-100 pb-5">
          <div className="flex items-center gap-3.5">
            <div className="h-12 w-12 overflow-hidden rounded-xl bg-white ring-2 ring-cobalt-100 shadow-subtle">
              <img
                src="/Recursos/FlucitoPerfil.jpeg?v=1"
                alt="Flucito"
                className="h-full w-full object-cover"
              />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-slate-900">Flucito</h1>
                <span className="inline-flex items-center rounded-md border border-cobalt-100 bg-cobalt-50 px-2 py-0.5 text-[11px] font-semibold text-cobalt-700">
                  React 19 + Tailwind v4
                </span>
              </div>
              <p className="text-xs font-medium text-slate-500">
                Asistente Virtual de Interflu • Fase 1 inicializada
              </p>
            </div>
          </div>
          <div className="rounded-lg bg-sidebar px-3 py-1.5 shadow-subtle">
            <img
              src="/Recursos/LogoInterflu.svg?v=1"
              alt="Interflu"
              className="h-7 w-auto object-contain"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-200/70 bg-slate-50/70 p-3.5 space-y-1">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-cobalt-700">
              <Layers className="h-4 w-4" />
              <span>Arquitectura</span>
            </div>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              Capas <code className="font-semibold text-slate-800">core</code>,{" "}
              <code className="font-semibold text-slate-800">schemas</code>,{" "}
              <code className="font-semibold text-slate-800">services</code> y{" "}
              <code className="font-semibold text-slate-800">components</code>.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200/70 bg-slate-50/70 p-3.5 space-y-1">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
              <ShieldCheck className="h-4 w-4" />
              <span>API Base</span>
            </div>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              Conectado a <code className="font-semibold text-slate-800">{API_V1_PREFIX}</code> con
              proxy local Vite.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200/70 bg-slate-50/70 p-3.5 space-y-1">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-cobalt-700">
              <Sparkles className="h-4 w-4" />
              <span>Design System</span>
            </div>
            <p className="text-[11px] text-slate-600 leading-relaxed">
              Tokens <code className="font-semibold text-slate-800">@theme</code> Cobalt y Plus
              Jakarta Sans activos.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between rounded-xl border border-emerald-200/80 bg-emerald-50/80 px-4 py-2.5 text-xs text-emerald-800">
          <span className="flex items-center gap-2 font-medium">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            Fase 1 lista para conectar AuthContext y servicios API (Fase 2)
          </span>
        </div>
      </div>
    </div>
  );
}
