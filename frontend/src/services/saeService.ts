import type { FiltroInventarioSae, PeriodoSae, ResumenComprasSae, ResumenFacturacionSae, ResumenInventarioSae } from "../schemas/sae";
import { apiFetch } from "./http";

function consultaPorPeriodo<T>(ruta: string, periodo: PeriodoSae | null, signal: AbortSignal) {
  const query = periodo ? `?${new URLSearchParams({ desde: periodo.desde, hasta: periodo.hasta })}` : "";
  return apiFetch<T>(`${ruta}${query}`, { signal, cache: "no-store" });
}

export function obtenerResumenSae(periodo: PeriodoSae | null, signal: AbortSignal) {
  return consultaPorPeriodo<ResumenComprasSae>("/sae/resumen", periodo, signal);
}

export function obtenerFacturacionSae(periodo: PeriodoSae | null, signal: AbortSignal) {
  return consultaPorPeriodo<ResumenFacturacionSae>("/sae/facturacion", periodo, signal);
}

export function obtenerInventarioSae(filtro: FiltroInventarioSae, signal: AbortSignal) {
  const query = new URLSearchParams({ estado: filtro.estado, pagina: String(filtro.pagina) });
  if (filtro.almacen) query.set("almacen", filtro.almacen);
  if (filtro.articulo.trim()) query.set("articulo", filtro.articulo.trim());
  return apiFetch<ResumenInventarioSae>(`/sae/inventario?${query}`, { signal, cache: "no-store" });
}
