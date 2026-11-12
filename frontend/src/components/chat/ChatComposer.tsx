import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { SendHorizontal, Sparkles } from "lucide-react";

interface ChatComposerProps {
  deshabilitado: boolean;
  mostrarSugerencias: boolean;
  onEnviar: (mensaje: string) => Promise<void>;
}

const SUGERENCIAS_RAPIDAS = [
  "Genera el reporte de entradas de hoy",
  "¿Qué facturas hay pendientes en Documentos Entrada?",
  "Busca en el catálogo SAE los artículos de la línea SMC",
  "Muéstrame los factores de precio actuales",
];

export function ChatComposer({
  deshabilitado,
  mostrarSugerencias,
  onEnviar,
}: ChatComposerProps) {
  const [texto, setTexto] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  function ajustarAlturaTextarea(el: HTMLTextAreaElement | null) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }

  async function manejarSubmit(e?: FormEvent) {
    if (e) e.preventDefault();
    const limpio = texto.trim();
    if (!limpio || deshabilitado) return;

    setTexto("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "42px";
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

  return (
    <div className="w-full space-y-2.5">
      {/* Sugerencias rápidas contextuales cuando la sesión está recién iniciada */}
      {mostrarSugerencias && !deshabilitado && (
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400 dark:text-slate-500 pr-1 flex-shrink-0">
            <Sparkles className="h-3 w-3 text-cobalt-500" />
            <span>Sugerencias:</span>
          </span>
          {SUGERENCIAS_RAPIDAS.map((sugerencia) => (
            <button
              key={sugerencia}
              type="button"
              onClick={() => void onEnviar(sugerencia)}
              className="flex-shrink-0 rounded-full border border-slate-200/90 dark:border-slate-700/80 bg-white dark:bg-dark-surface hover:border-cobalt-300 dark:hover:border-cobalt-600 hover:bg-cobalt-50/60 dark:hover:bg-dark-elevated px-3 py-1 text-xs font-medium text-slate-600 dark:text-slate-300 hover:text-cobalt-700 dark:hover:text-white active:scale-[0.98] transition-all cursor-pointer"
            >
              {sugerencia}
            </button>
          ))}
        </div>
      )}

      {/* Panel de entrada principal (diseño del prototipo sin controles innecesarios) */}
      <div
        className="w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-surface p-2.5 shadow-elevation transition-colors duration-200"
        data-purpose="chat-input-panel"
      >
        <form onSubmit={(e) => void manejarSubmit(e)} className="flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              rows={1}
              disabled={deshabilitado}
              value={texto}
              onChange={(e) => {
                setTexto(e.target.value);
                ajustarAlturaTextarea(e.target);
              }}
              onKeyDown={manejarKeyDown}
              placeholder="Escribe un mensaje a Flucito... (Enter para enviar, Shift+Enter para nueva línea)"
              style={{ minHeight: "42px", maxHeight: "140px" }}
              className="w-full resize-none bg-transparent py-2.5 pl-3 pr-3 text-sm text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 border-0 focus:ring-0 focus:outline-none disabled:opacity-60 custom-scroll"
            />
          </div>

          {/* Botón de Enviar (Azul cobalto característico del prototipo) */}
          <button
            type="submit"
            disabled={deshabilitado || !texto.trim()}
            aria-label="Enviar mensaje"
            title="Enviar mensaje (Enter)"
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-cobalt-600 hover:bg-cobalt-700 active:scale-[0.96] text-white shadow-md transition-all duration-150 disabled:opacity-45 disabled:pointer-events-none cursor-pointer"
          >
            <SendHorizontal className="h-4 w-4 ml-0.5" />
          </button>
        </form>
      </div>
    </div>
  );
}
