import type { PeriodoSae, ResumenComprasSae } from "../schemas/sae";
import { apiFetch } from "./http";

export function obtenerResumenSae(periodo: PeriodoSae | null, signal: AbortSignal) {
  const query = periodo ? `?${new URLSearchParams({ desde: periodo.desde, hasta: periodo.hasta })}` : "";
  return apiFetch<ResumenComprasSae>(`/sae/resumen${query}`, { signal, cache: "no-store" });
}
