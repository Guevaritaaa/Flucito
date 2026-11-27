import { useEffect, useState } from "react";
import type { PeriodoSae } from "../../schemas/sae";
import { obtenerFacturacionSae } from "../../services/saeService";
import { EstadoConsultaSae, FiltrosPeriodoSae, PreguntarSae, superficieSae, type ModuloSaeProps } from "./ControlesSae";
import { conteoSae, fechaSae, importeSae } from "./formatoSae";
import { TendenciaImportes } from "./TendenciaImportes";
import { useConsultaSae } from "./useConsultaSae";

export function PanelFacturacionSae({ creandoChat, onPreguntar, onRevalidarAcceso }: ModuloSaeProps) {
  const { resultado, cargando, error, aplicar, reintentar } = useConsultaSae(null, obtenerFacturacionSae, onRevalidarAcceso);
  const resumen = resultado?.datos;
  const [periodo, setPeriodo] = useState<PeriodoSae>({ desde: "", hasta: "" });
  const [monedaElegida, setMonedaElegida] = useState("");
  useEffect(() => { if (resumen) setPeriodo(resumen.periodo); }, [resumen]);

  const totales = resumen?.totales_por_moneda ?? [];
  const total = totales.find((valor) => valor.moneda === monedaElegida)
    ?? totales.find((valor) => valor.moneda === "MXN") ?? totales[0];
  const moneda = total?.moneda;
  const serie = resumen?.tendencia_mensual.map(({ mes, totales_por_moneda }) => ({
    mes,
    totales_por_moneda: totales_por_moneda.map((dato) => ({ moneda: dato.moneda, documentos: dato.facturas, importe: dato.importe_facturado })),
  })) ?? [];

  return (
    <div className="space-y-4">
      <EstadoConsultaSae error={error} cargando={cargando} onReintentar={reintentar}>Cargando facturación…</EstadoConsultaSae>
      {resumen && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-sm text-slate-700 dark:text-sky-100/80">
            <p>Facturas registradas hasta el {fechaSae(resumen.corte.cobertura.hasta)}</p>
            <PreguntarSae disabled={cargando || creandoChat} onClick={() => {
              const { desde, hasta } = resumen.periodo;
              onPreguntar(`Indica por separado el importe facturado y el importe de devoluciones de venta de Aspel SAE, con impuestos${moneda ? ` en ${moneda}` : ""}, del ${desde} al ${hasta}, inclusive.`);
            }} />
          </div>
          <FiltrosPeriodoSae periodo={periodo} cobertura={resumen.corte.cobertura} moneda={moneda}
            monedas={totales.map((dato) => dato.moneda)} cargando={cargando} etiqueta="Filtros de facturación"
            onPeriodo={setPeriodo} onMoneda={setMonedaElegida} onAplicar={() => aplicar(periodo)} />
          <section aria-labelledby="sae-facturacion" className="space-y-2.5">
            <div className="px-1">
              <h2 id="sae-facturacion" className="text-base font-bold">Facturación</h2>
              <p className="text-xs text-slate-600 dark:text-sky-100/75">Del {fechaSae(resumen.periodo.desde)} al {fechaSae(resumen.periodo.hasta)}</p>
            </div>
            <dl className={`${superficieSae} grid grid-cols-2 gap-px overflow-hidden @3xl:grid-cols-4`}>
              {[
                { titulo: "Facturas vigentes", valor: conteoSae.format(resumen.facturas), unidad: "Todas las monedas" },
                { titulo: "Importe facturado", valor: total ? importeSae(total.importe_facturado) : "—", unidad: moneda },
                { titulo: "Devoluciones de venta", valor: conteoSae.format(resumen.devoluciones), unidad: "Todas las monedas" },
                { titulo: "Importe de devoluciones", valor: total ? importeSae(total.importe_devoluciones) : "—", unidad: moneda },
              ].map(({ titulo, valor, unidad }) => (
                <div key={titulo} className="min-w-0 border-b border-slate-200/75 p-3.5 dark:border-sky-200/15 sm:p-4">
                  <dt className="text-sm text-slate-600 dark:text-sky-100/80">{titulo}</dt>
                  <dd className="mt-0.5 text-xl font-bold tabular-nums wrap-anywhere sm:text-2xl">{valor}</dd>
                  {unidad && <dd className="mt-1 text-xs text-slate-600 dark:text-sky-100/75">{unidad}</dd>}
                </div>
              ))}
            </dl>
          </section>
          {moneda ? (
            <TendenciaImportes key={`${resumen.periodo.desde}:${resumen.periodo.hasta}:${moneda}`} serie={serie} moneda={moneda} titulo="Facturación mensual" documentos="Facturas" />
          ) : (
            <p role="status" className={`${superficieSae} p-4 text-sm`}>No hay facturas vigentes ni devoluciones en el periodo seleccionado.</p>
          )}
        </>
      )}
    </div>
  );
}
