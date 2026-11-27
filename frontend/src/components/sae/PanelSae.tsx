import { MessageSquare } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { ACCESO_SAE_REQUERIDO } from "../../schemas/chat";
import type { PeriodoSae, ResumenComprasSae } from "../../schemas/sae";
import { ApiError } from "../../services/http";
import { obtenerResumenSae } from "../../services/saeService";
import { conteoSae, fechaSae, importeSae } from "./formatoSae";
import { TendenciaCompras } from "./TendenciaCompras";

interface PanelSaeProps {
  creandoChat: boolean;
  onPreguntar: (mensaje: string) => void;
  onRevalidarAcceso: (silencioso: boolean) => Promise<void>;
}

const campo = "block min-h-10 w-full min-w-0 rounded-lg border border-slate-300 bg-white/90 px-2 text-sm text-slate-900 outline-offset-2 focus-visible:outline-2 focus-visible:outline-blue-600 dark:border-sky-200/25 dark:bg-[#10254c] dark:text-white dark:focus-visible:outline-sky-300";

export function PanelSae({ creandoChat, onPreguntar, onRevalidarAcceso }: PanelSaeProps) {
  const [resumen, setResumen] = useState<ResumenComprasSae | null>(null);
  const [solicitud, setSolicitud] = useState<{ periodo: PeriodoSae | null }>({ periodo: null });
  const [periodo, setPeriodo] = useState<PeriodoSae>({ desde: "", hasta: "" });
  const [monedaElegida, setMonedaElegida] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCargando(true);
    setError(null);
    obtenerResumenSae(solicitud.periodo, controller.signal).then((datos) => {
      if (controller.signal.aborted) return;
      setResumen(datos);
      setPeriodo(datos.periodo);
    }).catch((err: unknown) => {
      if (controller.signal.aborted) return;
      if (err instanceof ApiError && (err.isForbidden || err.isUnauthorized)) {
        setResumen(null);
        setError(ACCESO_SAE_REQUERIDO);
        if (err.isForbidden) void onRevalidarAcceso(true);
      } else {
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el resumen de Aspel SAE.");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setCargando(false);
    });
    return () => controller.abort();
  }, [onRevalidarAcceso, solicitud]);

  const totales = resumen?.totales_por_moneda ?? [];
  const totalMoneda = totales.find((total) => total.moneda === monedaElegida)
    ?? totales.find((total) => total.moneda === "MXN") ?? totales[0];
  const moneda = totalMoneda?.moneda;
  const proveedores = resumen?.principales_proveedores.filter((item) => item.moneda === moneda) ?? [];

  function aplicarPeriodo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!cargando) setSolicitud({ periodo });
  }

  function preguntarPorPeriodo() {
    if (!resumen) return;
    const { desde, hasta } = resumen.periodo;
    const filtro = moneda ? ` en ${moneda}` : "";
    onPreguntar(`¿Cuál fue el importe total con impuestos de las compras vigentes${filtro} en Aspel SAE del ${desde} al ${hasta}, inclusive?`);
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-y-auto custom-scroll px-3 pt-2 pb-6 sm:px-6" aria-labelledby="sae-titulo">
      <div className="mx-auto w-full max-w-6xl space-y-4">
        <header className="flex flex-wrap items-end justify-between gap-3 px-1 pb-1">
          <div>
            <h1 id="sae-titulo" className="text-2xl font-extrabold tracking-tight sm:text-3xl">Aspel SAE</h1>
            {resumen && (
              <div className="mt-1 space-y-0.5 text-sm text-slate-700 dark:text-sky-100/80">
                <p>Empresa {resumen.corte.empresa}{resumen.corte.fecha_respaldo && ` · Respaldo del ${fechaSae(resumen.corte.fecha_respaldo)}`}</p>
                <p>Compras registradas hasta el {fechaSae(resumen.corte.cobertura.hasta)}</p>
              </div>
            )}
          </div>
          {resumen && (
            <button type="button" onClick={preguntarPorPeriodo} disabled={creandoChat || cargando}
              className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl bg-[#0022e6] px-3.5 text-sm font-semibold text-white hover:bg-[#0018cc] disabled:opacity-60 dark:bg-blue-700 dark:hover:bg-blue-600">
              <MessageSquare aria-hidden="true" className="size-4" /> Preguntar a Flucito
            </button>
          )}
        </header>

        {error && (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-300/90 bg-amber-50/95 p-3 text-sm text-amber-950 dark:border-amber-500/45 dark:bg-amber-950/75 dark:text-amber-100">
            <p className="min-w-0 flex-1">{error}</p>
            <button type="button" className="cursor-pointer rounded px-2 py-1 font-semibold underline" onClick={() => setSolicitud({ ...solicitud })} disabled={cargando}>Reintentar</button>
          </div>
        )}
        {cargando && <p role="status" className="px-1 text-sm text-slate-700 dark:text-sky-100/80">Cargando compras…</p>}

        {resumen && (
          <>
            <form onSubmit={aplicarPeriodo} aria-label="Filtros de compras" className="rounded-2xl border border-white/85 bg-white/80 p-3.5 dark:border-sky-300/15 dark:bg-[#0a1936]/85">
              <div className="flex flex-wrap items-end gap-2.5 sm:gap-3">
                <label className="flex min-w-[7.1rem] flex-1 flex-col gap-1 text-xs font-semibold sm:max-w-40">
                  Desde
                  <input type="date" required className={campo} disabled={cargando} value={periodo.desde}
                    min={resumen.corte.cobertura.desde} max={periodo.hasta || resumen.corte.cobertura.hasta}
                    onChange={(event) => setPeriodo({ ...periodo, desde: event.target.value })} />
                </label>
                <label className="flex min-w-[7.1rem] flex-1 flex-col gap-1 text-xs font-semibold sm:max-w-40">
                  Hasta
                  <input type="date" required className={campo} disabled={cargando} value={periodo.hasta}
                    min={periodo.desde || resumen.corte.cobertura.desde} max={resumen.corte.cobertura.hasta}
                    onChange={(event) => setPeriodo({ ...periodo, hasta: event.target.value })} />
                </label>
                <button type="submit" disabled={cargando} className="min-h-10 cursor-pointer rounded-lg border border-blue-700/30 bg-white/80 px-3 text-sm font-semibold text-blue-800 hover:bg-blue-50 disabled:opacity-60 dark:border-sky-300/30 dark:bg-[#10254c] dark:text-sky-200 dark:hover:bg-blue-900">
                  Aplicar periodo
                </button>
                {moneda && (
                  <label className="ms-auto flex min-w-20 flex-col gap-1 text-xs font-semibold">
                    Moneda
                    <select className={campo} value={moneda} onChange={(event) => setMonedaElegida(event.target.value)}>
                      {totales.map((total) => <option key={total.moneda}>{total.moneda}</option>)}
                    </select>
                  </label>
                )}
              </div>
            </form>

            <section aria-labelledby="sae-compras" className="space-y-2.5">
              <div className="px-1">
                <h2 id="sae-compras" className="text-base font-bold">Compras</h2>
                <p className="text-xs text-slate-600 dark:text-sky-100/75">Del {fechaSae(resumen.periodo.desde)} al {fechaSae(resumen.periodo.hasta)}</p>
              </div>
              <dl className="grid grid-cols-2 divide-x divide-y divide-slate-200/75 overflow-hidden rounded-2xl border border-white/85 bg-white/85 min-[560px]:grid-cols-3 min-[560px]:divide-y-0 dark:divide-sky-200/15 dark:border-sky-300/15 dark:bg-[#0a1936]/85">
                <div className={`min-w-0 p-3.5 sm:p-4 ${totalMoneda ? "col-span-2 min-[560px]:col-span-1" : "col-span-full"}`}>
                  <dt className="text-sm font-medium text-slate-600 dark:text-sky-100/80">Compras vigentes</dt>
                  <dd className="mt-0.5 text-2xl font-bold tabular-nums" data-testid="sae-documentos">{conteoSae.format(resumen.documentos)}</dd>
                  <dd className="mt-1 text-xs text-slate-600 dark:text-sky-100/75">Todas las monedas</dd>
                </div>
                {totalMoneda && (
                  <>
                    <div className="min-w-0 p-3.5 sm:p-4">
                      <dt className="text-sm font-medium text-slate-600 dark:text-sky-100/80">Importe con impuestos</dt>
                      <dd className="mt-0.5 text-xl font-bold tabular-nums sm:text-2xl" data-testid="sae-importe">{importeSae(totalMoneda.importe)}</dd>
                      <dd className="mt-1 text-xs text-slate-600 dark:text-sky-100/75">{moneda}</dd>
                    </div>
                    <div className="min-w-0 p-3.5 sm:p-4">
                      <dt className="text-sm font-medium text-slate-600 dark:text-sky-100/80">Compras en {moneda}</dt>
                      <dd className="mt-0.5 text-2xl font-bold tabular-nums" data-testid="sae-documentos-moneda">{conteoSae.format(totalMoneda.documentos)}</dd>
                    </div>
                  </>
                )}
              </dl>
            </section>

            {moneda ? (
              <div className="grid gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
                <TendenciaCompras key={`${resumen.periodo.desde}:${resumen.periodo.hasta}:${moneda}`} serie={resumen.tendencia_mensual} moneda={moneda} />
                <section aria-labelledby="sae-proveedores" className="min-w-0 rounded-2xl border border-white/85 bg-white/82 p-4 sm:p-5 dark:border-sky-300/15 dark:bg-[#0a1936]/85">
                  <h2 id="sae-proveedores" className="text-base font-bold">Principales proveedores</h2>
                  <p className="mt-1 text-sm text-slate-600 dark:text-sky-100/75">Por importe en {moneda}</p>
                  <ol className="mt-3 divide-y divide-slate-200/85 dark:divide-sky-200/15">
                    {proveedores.map((proveedor, indice) => (
                      <li key={proveedor.clave ?? indice} className="flex items-start justify-between gap-3 py-2.5 text-sm">
                        <div className="flex min-w-0 items-start gap-2.5">
                          <span className="min-w-4 shrink-0 text-xs leading-5 font-semibold tabular-nums text-slate-600 dark:text-sky-100/70">{indice + 1}</span>
                          <div className="min-w-0 wrap-anywhere">
                            <p className="font-semibold">{proveedor.nombre ?? proveedor.clave ?? "Proveedor sin registrar"}</p>
                            <p className="text-xs text-slate-600 dark:text-sky-100/75">{conteoSae.format(proveedor.documentos)} {proveedor.documentos === 1 ? "compra" : "compras"}</p>
                          </div>
                        </div>
                        <span className="shrink-0 font-semibold tabular-nums">{importeSae(proveedor.importe)}</span>
                      </li>
                    ))}
                  </ol>
                </section>
              </div>
            ) : (
              <p role="status" className="rounded-2xl border border-white/85 bg-white/80 p-4 text-sm text-slate-700 dark:border-sky-300/15 dark:bg-[#0a1936]/85 dark:text-sky-100/80">No hay compras vigentes en el periodo seleccionado.</p>
            )}
          </>
        )}
      </div>
    </main>
  );
}
