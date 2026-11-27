import { MessageSquare } from "lucide-react";
import type { ReactNode } from "react";
import type { PeriodoSae } from "../../schemas/sae";

export const campoSae = "block min-h-10 w-full min-w-0 rounded-lg border border-slate-300 bg-white/90 px-2 text-sm text-slate-900 outline-offset-2 focus-visible:outline-2 focus-visible:outline-blue-600 dark:border-sky-200/25 dark:bg-[#10254c] dark:text-white dark:focus-visible:outline-sky-300";
export const botonSae = "min-h-10 cursor-pointer rounded-lg border border-blue-700/30 bg-white/80 px-3 text-sm font-semibold text-blue-800 hover:bg-blue-50 disabled:opacity-60 dark:border-sky-300/30 dark:bg-[#10254c] dark:text-sky-200 dark:hover:bg-blue-900";
export const superficieSae = "rounded-2xl border border-white/85 bg-white/82 dark:border-sky-300/15 dark:bg-[#0a1936]/85";

export interface ModuloSaeProps {
  creandoChat: boolean;
  onPreguntar: (mensaje: string) => void;
  onRevalidarAcceso: (silencioso: boolean) => Promise<void>;
}

export function PreguntarSae({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl bg-[#0022e6] px-3.5 text-sm font-semibold text-white hover:bg-[#0018cc] disabled:opacity-60 dark:bg-blue-700 dark:hover:bg-blue-600">
      <MessageSquare aria-hidden="true" className="size-4" /> Preguntar a Flucito
    </button>
  );
}

export function EstadoConsultaSae({ error, cargando, onReintentar, children }: {
  error: string | null; cargando: boolean; onReintentar: () => void; children: ReactNode;
}) {
  return (
    <>
      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-300/90 bg-amber-50/95 p-3 text-sm text-amber-950 dark:border-amber-500/45 dark:bg-amber-950/75 dark:text-amber-100">
          <p className="min-w-0 flex-1">{error}</p>
          <button type="button" className="cursor-pointer rounded px-2 py-1 font-semibold underline" onClick={onReintentar} disabled={cargando}>Reintentar</button>
        </div>
      )}
      {cargando && <p role="status" className="px-1 text-sm text-slate-700 dark:text-sky-100/80">{children}</p>}
    </>
  );
}

export function FiltrosPeriodoSae({ periodo, cobertura, moneda, monedas, cargando, onPeriodo, onMoneda, onAplicar, etiqueta }: {
  periodo: PeriodoSae; cobertura: PeriodoSae; moneda?: string; monedas: string[]; cargando: boolean;
  onPeriodo: (periodo: PeriodoSae) => void; onMoneda: (moneda: string) => void; onAplicar: () => void; etiqueta: string;
}) {
  return (
    <form onSubmit={(event) => { event.preventDefault(); if (!cargando) onAplicar(); }} aria-label={etiqueta} className={`${superficieSae} p-3.5`}>
      <div className="flex flex-wrap items-end gap-2.5 sm:gap-3">
        <label className="flex min-w-[7.1rem] flex-1 flex-col gap-1 text-xs font-semibold sm:max-w-40">
          Desde
          <input type="date" required className={campoSae} disabled={cargando} value={periodo.desde}
            min={cobertura.desde} max={periodo.hasta || cobertura.hasta}
            onChange={(event) => onPeriodo({ ...periodo, desde: event.target.value })} />
        </label>
        <label className="flex min-w-[7.1rem] flex-1 flex-col gap-1 text-xs font-semibold sm:max-w-40">
          Hasta
          <input type="date" required className={campoSae} disabled={cargando} value={periodo.hasta}
            min={periodo.desde || cobertura.desde} max={cobertura.hasta}
            onChange={(event) => onPeriodo({ ...periodo, hasta: event.target.value })} />
        </label>
        <button type="submit" disabled={cargando} className={botonSae}>Aplicar periodo</button>
        {moneda && (
          <label className="ms-auto flex min-w-20 flex-col gap-1 text-xs font-semibold">
            Moneda
            <select className={campoSae} value={moneda} onChange={(event) => onMoneda(event.target.value)}>
              {monedas.map((codigo) => <option key={codigo}>{codigo}</option>)}
            </select>
          </label>
        )}
      </div>
    </form>
  );
}
