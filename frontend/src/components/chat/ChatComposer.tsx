import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import {
  ArrowUp,
  FileSpreadsheet,
  FileText,
  Search,
  SlidersHorizontal,
} from "lucide-react";

interface ChatComposerProps {
  deshabilitado: boolean;
  variante?: "hero" | "docked";
  onEnviar: (mensaje: string) => Promise<void>;
}

export const SUGERENCIAS_RAPIDAS = [
  {
    etiqueta: "Reporte de almacén",
    prompt: "Genera el reporte de entradas de hoy",
    icono: FileSpreadsheet,
  },
  {
    etiqueta: "Facturas pendientes",
    prompt: "¿Qué facturas hay pendientes en Documentos Entrada?",
    icono: FileText,
  },
  {
    etiqueta: "Catálogo línea SMC",
    prompt: "Busca en el catálogo SAE los artículos de la línea SMC",
    icono: Search,
  },
  {
    etiqueta: "Factores de precio",
    prompt: "Muéstrame los factores de precio actuales",
    icono: SlidersHorizontal,
  },
] as const;

export function ChatComposer({
  deshabilitado,
  variante = "docked",
  onEnviar,
}: ChatComposerProps) {
  const [texto, setTexto] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  function ajustarAlturaTextarea(el: HTMLTextAreaElement | null) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 152)}px`;
  }

  async function manejarSubmit(e?: FormEvent) {
    if (e) e.preventDefault();
    const limpio = texto.trim();
    if (!limpio || deshabilitado) return;

    setTexto("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "44px";
    }
    await onEnviar(limpio);
    textareaRef.current?.focus();
  }

  function manejarKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void manejarSubmit();
    }
  }

  const esHero = variante === "hero";

  return (
    <div className="w-full space-y-3">
      {/* Cápsula de entrada de cristal esmerilado estilo ChatGPT + LoginView */}
      <div
        className={`w-full rounded-[24px] border border-white/90 dark:border-sky-300/22 bg-white/82 dark:bg-[#0a1936]/84 backdrop-blur-xl transition-all duration-200 focus-within:border-[#0022e6]/45 dark:focus-within:border-sky-300/45 focus-within:bg-white/92 dark:focus-within:bg-[#0a1936]/92 ${
          esHero
            ? "p-2.5 sm:p-3 shadow-[0_16px_40px_rgba(12,50,110,0.1)] dark:shadow-[0_20px_46px_rgba(2,8,26,0.58)]"
            : "p-2 sm:p-2.5 shadow-[0_12px_32px_rgba(12,50,110,0.08)] dark:shadow-[0_16px_38px_rgba(2,8,26,0.5)]"
        }`}
        data-purpose="chat-input-panel"
      >
        <form
          onSubmit={(e) => void manejarSubmit(e)}
          className="flex items-end gap-2"
        >
          <div className="relative flex-1 min-w-0">
            <textarea
              ref={textareaRef}
              rows={1}
              aria-label="Mensaje para Flucito"
              disabled={deshabilitado}
              value={texto}
              onChange={(e) => {
                setTexto(e.target.value);
                ajustarAlturaTextarea(e.target);
              }}
              onKeyDown={manejarKeyDown}
              placeholder="Escribe un mensaje a Flucito..."
              style={{ minHeight: "44px", maxHeight: "clamp(44px, 25cqh, 152px)" }}
              className="w-full resize-none bg-transparent py-2.5 pl-3.5 pr-2 text-base md:text-[15px] pointer-coarse:text-base leading-relaxed text-slate-900 dark:text-white placeholder-slate-500 dark:placeholder-sky-200/60 caret-[#0022e6] dark:caret-sky-400 border-0 focus:ring-0 focus:outline-none disabled:opacity-60 custom-scroll"
            />
          </div>

          {/* Botón de Enviar estilo ChatGPT con el azul cobalto de LoginView */}
          <button
            type="submit"
            disabled={deshabilitado || !texto.trim()}
            aria-label="Enviar mensaje"
            title="Enviar mensaje (Enter)"
            className="mb-0.5 flex h-11 w-11 sm:h-10 sm:w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-[#0022e6] hover:bg-[#0018cc] dark:bg-[#1d4ed8] dark:hover:bg-[#2563eb] active:scale-[0.95] text-white shadow-[0_6px_18px_rgba(0,34,230,0.32)] dark:shadow-[0_6px_20px_rgba(29,78,216,0.45)] transition-all duration-150 disabled:opacity-35 disabled:shadow-none disabled:pointer-events-none cursor-pointer"
          >
            <ArrowUp className="h-4.5 w-4.5 stroke-[2.4]" />
          </button>
        </form>
      </div>

      {/* Chips de acciones reales debajo del compositor cuando la conversación está recién iniciada */}
      {esHero && (
        <div
          className="chat-suggestions flex flex-wrap items-center justify-center gap-2 pt-0.5"
          aria-label="Sugerencias rápidas"
        >
          {SUGERENCIAS_RAPIDAS.map((item) => {
            const Icon = item.icono;
            return (
              <button
                key={item.etiqueta}
                type="button"
                disabled={deshabilitado}
                onClick={() => void onEnviar(item.prompt)}
                title={item.prompt}
                className="inline-flex items-center gap-2 rounded-full border border-white/85 dark:border-sky-300/20 bg-white/70 dark:bg-[#0e2248]/70 hover:bg-white/95 dark:hover:bg-[#152f61]/90 backdrop-blur-md px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-sky-100 hover:text-[#0022e6] dark:hover:text-white active:scale-[0.98] transition-all duration-150 disabled:opacity-50 cursor-pointer"
              >
                <Icon className="h-3.5 w-3.5 text-[#0022e6] dark:text-sky-300 flex-shrink-0" />
                <span>{item.etiqueta}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
