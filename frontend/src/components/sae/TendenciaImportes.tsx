import { useState } from "react";
import type { ComprasMes } from "../../schemas/sae";
import { conteoSae, etiquetaMesSae, importeSae, mesSae } from "./formatoSae";

export function TendenciaImportes({ serie, moneda, titulo = "Tendencia mensual", documentos = "Compras" }: {
  serie: ComprasMes[]; moneda: string; titulo?: string; documentos?: string;
}) {
  const datos = serie.map(({ mes, totales_por_moneda }) => {
    const total = totales_por_moneda.find((item) => item.moneda === moneda);
    return { mes, documentos: total?.documentos ?? 0, importe: total?.importe ?? "0.00" };
  });
  const [mesElegido, setMesElegido] = useState<string>();
  const seleccionado = datos.find((dato) => dato.mes === mesElegido) ?? datos.at(-1);
  const alturas = datos.map((dato) => Number(dato.importe));
  const minimo = Math.min(0, ...alturas);
  const escala = Math.max(0, ...alturas) - minimo || 1;
  const cero = (-minimo / escala) * 100;

  return (
    <section aria-labelledby="sae-tendencia" className="min-w-0 rounded-2xl border border-white/85 bg-white/82 p-4 sm:p-5 dark:border-sky-300/15 dark:bg-[#0a1936]/85">
      <h2 id="sae-tendencia" className="text-base font-bold">{titulo}</h2>
      {seleccionado && (
        <p aria-live="polite" className="mt-1 text-sm text-slate-600 dark:text-sky-100/75">
          <span className="inline-block first-letter:uppercase">{mesSae(seleccionado.mes)}</span>{" · "}
          <strong className="font-semibold text-slate-900 dark:text-white">{importeSae(seleccionado.importe)} {moneda}</strong>
        </p>
      )}
      <div className="mt-4 overflow-x-auto custom-scroll pb-1">
        <div className="relative flex gap-1.5" style={{ minWidth: `${datos.length * 2.4}rem` }}>
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-35">
            <div className="absolute inset-x-0 border-t border-slate-400/75 dark:border-sky-200/35" style={{ bottom: `${cero}%` }} />
          </div>
          {datos.map((dato, index) => {
            const valor = alturas[index];
            const activo = seleccionado?.mes === dato.mes;
            return (
              <button
                key={dato.mes}
                type="button"
                aria-pressed={activo}
                aria-label={`${mesSae(dato.mes)}, ${importeSae(dato.importe)} ${moneda}, ${conteoSae.format(dato.documentos)} ${documentos.toLowerCase()}`}
                onClick={() => setMesElegido(dato.mes)}
                className="flex min-w-0 flex-1 cursor-pointer flex-col items-stretch rounded-lg px-1 text-xs text-slate-600 outline-offset-[-2px] hover:bg-sky-100/65 focus-visible:outline-2 focus-visible:outline-blue-600 dark:text-sky-100/80 dark:hover:bg-sky-400/12 dark:focus-visible:outline-sky-300"
              >
                <span aria-hidden="true" className="relative mx-auto block h-35 w-full max-w-11">
                  <span
                    className={`absolute inset-x-0 min-h-px rounded-sm ${activo ? "bg-[#0022e6] dark:bg-sky-300" : "bg-blue-400 dark:bg-sky-600"}`}
                    style={{ bottom: `${((Math.min(0, valor) - minimo) / escala) * 100}%`, height: `${(Math.abs(valor) / escala) * 100}%` }}
                  />
                </span>
                <span aria-hidden="true" className="mt-1 py-2 capitalize">{etiquetaMesSae(dato.mes)}</span>
              </button>
            );
          })}
        </div>
      </div>
      <details className="mt-2 border-t border-slate-200/90 pt-2 dark:border-sky-200/15">
        <summary className="w-fit cursor-pointer rounded py-1 text-sm font-semibold text-blue-800 dark:text-sky-300">Ver datos mensuales</summary>
        <table className="mt-2 w-full text-left text-sm tabular-nums">
          <caption className="sr-only">Importe y {documentos.toLowerCase()} por mes en {moneda}</caption>
          <thead className="text-xs text-slate-600 dark:text-sky-100/75">
            <tr><th scope="col" className="py-1">Mes</th><th scope="col" className="py-1 text-right">{documentos}</th><th scope="col" className="py-1 text-right">Importe ({moneda})</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-200/80 dark:divide-sky-200/12">
            {datos.map((dato) => (
              <tr key={dato.mes}>
                <th scope="row" className="py-2 text-xs font-medium first-letter:uppercase">{mesSae(dato.mes)}</th>
                <td className="py-2 pl-2 text-right">{conteoSae.format(dato.documentos)}</td>
                <td className="py-2 pl-2 text-right">{importeSae(dato.importe)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
