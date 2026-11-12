import { useEffect, useRef } from "react";
import { useChat } from "../../hooks/useChat";
import { ChatComposer } from "./ChatComposer";
import { FlucitoLoadingBubble, MessageBubble } from "./MessageBubble";

interface ChatWorkspaceProps {
  sessionId: string;
  existeEnHistorial: boolean;
  tituloConversacion?: string | null;
  onConversacionActualizada: () => void;
}

export function ChatWorkspace({
  sessionId,
  existeEnHistorial,
  tituloConversacion,
  onConversacionActualizada,
}: ChatWorkspaceProps) {
  const { mensajes, enviando, cargandoMensajes, enviarMensaje } = useChat({
    sessionId,
    existeEnHistorial,
    onConversacionActualizada,
  });

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [mensajes, enviando]);

  const mostrarSugerencias = mensajes.length <= 1 && !existeEnHistorial;

  return (
    <main
      className="mx-auto flex flex-1 w-full max-w-5xl flex-col justify-between overflow-hidden px-4 sm:px-6 pt-5 pb-3"
      data-purpose="chat-container"
    >
      {/* Hilo de mensajes */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto custom-scroll space-y-6 pr-2 mb-4"
        data-purpose="message-history"
      >
        {/* Píldora superior de estado de sesión */}
        <div className="text-center my-1.5">
          <span className="inline-block rounded-full bg-slate-200/70 dark:bg-dark-elevated px-3.5 py-1 text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {tituloConversacion ? tituloConversacion : "Sesión activa"}
          </span>
        </div>

        {cargandoMensajes ? (
          <div className="space-y-4 py-6" aria-label="Cargando mensajes de la conversación">
            <div className="flex justify-end">
              <div className="h-12 w-64 rounded-2xl bg-slate-200/70 dark:bg-dark-elevated animate-pulse" />
            </div>
            <div className="flex items-start gap-3">
              <div className="h-8 w-8 rounded-full bg-slate-200/70 dark:bg-dark-elevated animate-pulse" />
              <div className="h-24 w-96 max-w-full rounded-2xl bg-slate-200/70 dark:bg-dark-elevated animate-pulse" />
            </div>
          </div>
        ) : (
          <>
            {mensajes.map((msg) => (
              <MessageBubble key={msg.id} mensaje={msg} />
            ))}
            {enviando && <FlucitoLoadingBubble />}
          </>
        )}
      </div>

      {/* Compositor de mensajes */}
      <ChatComposer
        deshabilitado={enviando || cargandoMensajes}
        mostrarSugerencias={mostrarSugerencias}
        onEnviar={enviarMensaje}
      />

      {/* Nota legal y pie de advertencia del prototipo */}
      <div className="text-center pt-2">
        <p className="text-[11px] text-slate-400 dark:text-slate-500">
          Flucito puede cometer errores. Verifica la información. • Interflu AI
        </p>
      </div>
    </main>
  );
}
