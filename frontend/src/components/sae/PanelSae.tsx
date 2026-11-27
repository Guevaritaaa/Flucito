import { useState } from "react";
import type { ModuloSaeProps } from "./ControlesSae";
import { PanelComprasSae } from "./PanelComprasSae";
import { PanelFacturacionSae } from "./PanelFacturacionSae";
import { PanelInventarioSae } from "./PanelInventarioSae";

const modulos = [
  { titulo: "Compras", Panel: PanelComprasSae },
  { titulo: "Facturación", Panel: PanelFacturacionSae },
  { titulo: "Inventario", Panel: PanelInventarioSae },
] as const;

export function PanelSae(props: ModuloSaeProps) {
  const [activo, setActivo] = useState<(typeof modulos)[number]>(modulos[0]);

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-y-auto custom-scroll px-3 pt-2 pb-6 sm:px-6" aria-labelledby="sae-titulo">
      <div className="mx-auto w-full max-w-6xl space-y-4">
        <header className="flex flex-wrap items-end justify-between gap-3 px-1 pb-1">
          <div>
            <h1 id="sae-titulo" className="text-2xl font-extrabold tracking-tight sm:text-3xl">Aspel SAE</h1>
            <p className="mt-1 text-sm text-slate-700 dark:text-sky-100/80">Empresa 02</p>
          </div>
          <nav aria-label="Módulos de Aspel SAE" className="inline-flex max-w-full flex-wrap gap-0.5 rounded-xl border border-white/85 bg-white/75 p-1 text-sm dark:border-sky-300/15 dark:bg-[#0a1936]/85">
            {modulos.map((modulo) => (
              <button key={modulo.titulo} type="button" aria-pressed={activo === modulo} onClick={() => setActivo(modulo)}
                className={`min-h-9 cursor-pointer rounded-lg px-3 font-semibold ${activo === modulo
                  ? "bg-blue-100 text-blue-900 dark:bg-sky-400/22 dark:text-white"
                  : "text-slate-700 hover:bg-blue-50 dark:text-sky-100/80 dark:hover:bg-sky-400/12"}`}>
                {modulo.titulo}
              </button>
            ))}
          </nav>
        </header>
        <activo.Panel {...props} />
      </div>
    </main>
  );
}
