import { useEffect, useState } from "react";
import type { PeriodoSae } from "../../schemas/sae";
import { obtenerResumenSae } from "../../services/saeService";
import { EstadoConsultaSae, FiltrosPeriodoSae, PreguntarSae, type ModuloSaeProps } from "./ControlesSae";
import { conteoSae, fechaSae, importeSae } from "./formatoSae";
import { TendenciaImportes } from "./TendenciaImportes";
import { useConsultaSae } from "./useConsultaSae";

export function PanelComprasSae({ creandoChat, onPreguntar, onRevalidarAcceso }: ModuloSaeProps) {
  const { resultado, cargando, error, aplicar, reintentar } = useConsultaSae(null, obtenerResumenSae, onRevalidarAcceso);
  const resumen = resultado?.datos;
  const [periodo, setPeriodo] = useState<PeriodoSae>({ desde: "", hasta: "" });
  const [monedaElegida, setMonedaElegida] = useState("");

  useEffect(() => {
    if (resumen) setPeriodo(resumen.periodo);
  }, [resumen]);

  const totales = resumen?.totales_por_moneda ?? [];
  const totalMoneda = totales.find((total) => total.moneda === monedaElegida)
    ?? totales.find((total) => total.moneda === "MXN") ?? totales[0];
  const moneda = totalMoneda?.moneda;
  const proveedores = resumen?.principales_proveedores.filter((item) => item.moneda === moneda) ?? [];

  function preguntarPorPeriodo() {
    if (!resumen) return;
    const { desde, hasta } = resumen.periodo;
    const filtro = moneda ? ` en ${moneda}` : "";
    onPreguntar(`¿Cuál fue el importe total con impuestos de las compras vigentes${filtro} en Aspel SAE del ${desde} al ${hasta}, inclusive?`);
  }

  return (
    <div className="space-y-4">
        <EstadoConsultaSae error={error} cargando={cargando} onReintentar={reintentar}>Cargando compras…</EstadoConsultaSae>

        {resumen && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-sm text-slate-700 dark:text-sky-100/80">
              <div>
                {resumen.corte.fecha_respaldo && <p>Respaldo del {fechaSae(resumen.corte.fecha_respaldo)}</p>}
                <p>Compras registradas hasta el {fechaSae(resumen.corte.cobertura.hasta)}</p>
              </div>
              <PreguntarSae onClick={preguntarPorPeriodo} disabled={creandoChat || cargando} />
            </div>
            <FiltrosPeriodoSae periodo={periodo} cobertura={resumen.corte.cobertura} moneda={moneda}
              monedas={totales.map((total) => total.moneda)} cargando={cargando} etiqueta="Filtros de compras"
              onPeriodo={setPeriodo} onMoneda={setMonedaElegida} onAplicar={() => aplicar(periodo)} />

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
                <TendenciaImportes key={`${resumen.periodo.desde}:${resumen.periodo.hasta}:${moneda}`} serie={resumen.tendencia_mensual} moneda={moneda} />
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
  );
}
