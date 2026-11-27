import { useState } from "react";
import type { EstadoInventarioSae, FiltroInventarioSae } from "../../schemas/sae";
import { obtenerInventarioSae } from "../../services/saeService";
import { botonSae, campoSae, EstadoConsultaSae, PreguntarSae, superficieSae, type ModuloSaeProps } from "./ControlesSae";
import { cantidadSae, conteoSae, fechaSae } from "./formatoSae";
import { useConsultaSae } from "./useConsultaSae";

const filtroInicial: FiltroInventarioSae = { almacen: "", articulo: "", estado: "todos", pagina: 1 };

export function PanelInventarioSae({ creandoChat, onPreguntar, onRevalidarAcceso }: ModuloSaeProps) {
  const { resultado, cargando, error, aplicar, reintentar } = useConsultaSae(filtroInicial, obtenerInventarioSae, onRevalidarAcceso);
  const [filtros, setFiltros] = useState(filtroInicial);
  const resumen = resultado?.datos;

  function preguntarAlCorte() {
    if (!resultado) return;
    const almacen = resultado.datos.almacen;
    const ubicacion = almacen ? `en el almacén ${almacen.clave}` : "en el inventario global";
    const articulo = resultado.filtro.articulo.trim();
    const estado = resultado.filtro.estado;
    const condicion = estado === "sin_existencia" ? " sin existencia" : estado === "bajo_minimo" ? " bajo mínimo" : "";
    if (articulo || condicion) {
      const coincidencia = articulo ? ` que coinciden con «${articulo}»` : "";
      onPreguntar(`Muestra las existencias al corte de Aspel SAE ${ubicacion} para los artículos${condicion}${coincidencia}.`);
    } else {
      onPreguntar(`¿Cuántos artículos están sin existencia y cuántos están bajo mínimo ${ubicacion} al corte de Aspel SAE?`);
    }
  }

  return (
    <div className="space-y-4">
      <EstadoConsultaSae error={error} cargando={cargando} onReintentar={reintentar}>Cargando inventario…</EstadoConsultaSae>
      {resultado && resumen && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-sm text-slate-700 dark:text-sky-100/80">
            <div>
              <p>Existencias al corte del respaldo</p>
              {resumen.corte.ultimo_movimiento && <p className="text-xs">Último movimiento registrado el {fechaSae(resumen.corte.ultimo_movimiento)}</p>}
            </div>
            <PreguntarSae disabled={creandoChat || cargando} onClick={preguntarAlCorte} />
          </div>

          <form aria-label="Filtros de inventario" className={`${superficieSae} flex flex-wrap items-end gap-2.5 p-3.5`} onSubmit={(event) => {
            event.preventDefault();
            if (!cargando) aplicar({ ...filtros, pagina: 1 });
          }}>
            <label className="min-w-35 flex-1 space-y-1 text-xs font-semibold">
              Almacén
              <select className={campoSae} value={filtros.almacen} disabled={cargando} onChange={(event) => setFiltros({ ...filtros, almacen: event.target.value })}>
                <option value="">Inventario global</option>
                {resumen.almacenes.map((almacen) => <option key={almacen.clave} value={almacen.clave}>{almacen.clave} · {almacen.nombre}</option>)}
              </select>
            </label>
            <label className="min-w-32 flex-1 space-y-1 text-xs font-semibold">
              Artículo
              <input className={campoSae} placeholder="Clave o nombre" value={filtros.articulo} maxLength={100} disabled={cargando}
                onChange={(event) => setFiltros({ ...filtros, articulo: event.target.value })} />
            </label>
            <label className="min-w-32 flex-1 space-y-1 text-xs font-semibold">
              Estado
              <select className={campoSae} value={filtros.estado} disabled={cargando}
                onChange={(event) => setFiltros({ ...filtros, estado: event.target.value as EstadoInventarioSae })}>
                <option value="todos">Todos</option>
                <option value="sin_existencia">Sin existencia</option>
                <option value="bajo_minimo">Bajo mínimo</option>
              </select>
            </label>
            <button type="submit" className={botonSae} disabled={cargando}>Aplicar filtros</button>
          </form>

          <section aria-labelledby="sae-existencias" className="space-y-2.5">
            <div className="px-1">
              <h2 id="sae-existencias" className="text-base font-bold">Existencias</h2>
              <p className="text-xs text-slate-600 dark:text-sky-100/75">
                {resumen.almacen ? `${resumen.almacen.clave} · ${resumen.almacen.nombre}` : "Inventario global"}
              </p>
            </div>
            <dl className={`${superficieSae} grid grid-cols-3 divide-x divide-slate-200/75 dark:divide-sky-200/15`}>
              {[
                { titulo: "Artículos activos", valor: resumen.articulos },
                { titulo: "Sin existencia", valor: resumen.sin_existencia },
                { titulo: "Bajo mínimo", valor: resumen.bajo_minimo },
              ].map(({ titulo, valor }) => (
                <div className="min-w-0 p-2.5 sm:p-4" key={titulo}>
                  <dt className="text-xs font-medium text-slate-600 dark:text-sky-100/80 sm:text-sm">{titulo}</dt>
                  <dd className="mt-1 text-lg font-bold tabular-nums sm:text-2xl">{conteoSae.format(valor)}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section aria-labelledby="sae-articulos" className={`${superficieSae} min-w-0 p-3.5 sm:p-5`}>
            <h2 id="sae-articulos" className="text-base font-bold">Artículos</h2>
            {resumen.existencias.length ? (
              <div className="mt-2 overflow-x-auto custom-scroll">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-xs text-slate-600 dark:text-sky-100/75">
                    <tr>
                      <th scope="col" className="py-2 pr-2">Artículo</th>
                      <th scope="col" className="py-2 pr-2">Unidad</th>
                      <th scope="col" className="py-2 pr-2 text-right">Existencia</th>
                      <th scope="col" className="py-2 text-right">Mínimo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200/75 dark:divide-sky-200/15">
                    {resumen.existencias.map((articulo) => (
                      <tr key={articulo.clave}>
                        <th scope="row" className="max-w-sm py-2 pr-2 font-semibold wrap-anywhere">
                          {articulo.nombre ?? articulo.clave}
                          {articulo.nombre && <code className="block whitespace-pre-wrap text-xs font-normal text-slate-600 dark:text-sky-100/75">{articulo.clave}</code>}
                        </th>
                        <td className="py-2 pr-2">{articulo.unidad || "—"}</td>
                        <td className="py-2 pr-2 text-right tabular-nums">{cantidadSae(articulo.existencia)}</td>
                        <td className="py-2 text-right tabular-nums">{cantidadSae(articulo.minimo)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p role="status" className="mt-2 text-sm">No hay artículos con los filtros aplicados.</p>}
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/80 pt-3 dark:border-sky-200/15">
              <p className="text-xs text-slate-600 dark:text-sky-100/75">{conteoSae.format(resumen.total_resultados)} resultados</p>
              {resumen.total_resultados > resumen.por_pagina && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <button type="button" className={botonSae} disabled={cargando || resumen.pagina === 1}
                    onClick={() => aplicar({ ...resultado.filtro, pagina: resumen.pagina - 1 })}>Anterior</button>
                  <span>Página {conteoSae.format(resumen.pagina)}</span>
                  <button type="button" className={botonSae} disabled={cargando || resumen.pagina * resumen.por_pagina >= resumen.total_resultados}
                    onClick={() => aplicar({ ...resultado.filtro, pagina: resumen.pagina + 1 })}>Siguiente</button>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
