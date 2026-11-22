import { useEffect, useRef } from "react";
import { ASSETS } from "../../core/config";
import { useChat } from "../../hooks/useChat";
import { ChatComposer } from "./ChatComposer";
import { FlucitoLoadingBubble, MessageBubble } from "./MessageBubble";

interface ChatWorkspaceProps {
  sessionId: string;
  existeEnHistorial: boolean;
  onConversacionActualizada: () => void;
}

export function ChatWorkspace({
  sessionId,
  existeEnHistorial,
  onConversacionActualizada,
}: ChatWorkspaceProps) {
  const { mensajes, enviando, actividades, etapa, cargandoMensajes, enviarMensaje } = useChat({
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

  const esEstadoInicial =
    !cargandoMensajes && !existeEnHistorial && mensajes.length === 0 && !enviando;

  return (
    <main
      className="relative flex flex-1 w-full flex-col justify-between overflow-hidden px-4 sm:px-6 pb-3"
      data-purpose="chat-container"
    >
      {esEstadoInicial ? (
        /* ESTADO 1: Escena centrada estilo ChatGPT en Glassmorphism (Nuevo chat vacío) */
        <div className="flex flex-1 min-h-0 w-full overflow-y-auto custom-scroll">
          <div className="flex w-full max-w-2xl flex-col items-center justify-center m-auto py-6 animate-stage-in">
          {/* Retrato espacial de Flucito 3D con halo refractivo */}
          <div className="relative mb-4 flex items-center justify-center">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -inset-3 rounded-full bg-cyan-300/45 dark:bg-sky-400/25 blur-xl"
            />
            <div className="relative h-24 w-24 sm:h-28 sm:w-28 overflow-hidden rounded-full border-2 border-white/90 dark:border-sky-300/35 bg-gradient-to-b from-sky-100/90 via-white/80 to-cyan-100/85 dark:from-[#163870] dark:via-[#0e244d] dark:to-[#0a1936] shadow-[0_14px_34px_rgba(14,90,170,0.18)] dark:shadow-[0_16px_38px_rgba(0,0,0,0.5)]">
              <img
                src={ASSETS.FLUCITO_3D}
                alt="Flucito - Asistente Virtual de Interflu"
                width={112}
                height={112}
                className="h-full w-full object-cover object-top scale-[1.22] translate-y-1.5 select-none pointer-events-none"
              />
            </div>
          </div>

          {/* Saludo centrado */}
          <div className="text-center space-y-1.5 mb-6 sm:mb-7">
            <h1 className="text-2xl sm:text-[30px] font-extrabold tracking-tight text-slate-900 dark:text-white leading-tight">
              ¡Hola! Soy Flucito
            </h1>
            <p className="text-sm sm:text-[15px] font-medium text-slate-600 dark:text-sky-100/80">
              ¿Cómo te puedo ayudar hoy en Interflu?
            </p>
          </div>

          {/* Compositor centrado + chips reales justo debajo */}
          <ChatComposer
            variante="hero"
            autoFocus
            deshabilitado={enviando || cargandoMensajes}
            onEnviar={enviarMensaje}
          />
          </div>
        </div>
      ) : (
        /* ESTADO 2: Conversación activa estilo ChatGPT (hilo centrado + barra anclada al pie) */
        <>
          <div
            ref={scrollContainerRef}
            className="flex-1 w-full overflow-y-auto custom-scroll pt-3 pb-4"
            data-purpose="message-history"
          >
            <div className="mx-auto w-full max-w-3xl space-y-5 pr-1">
              {cargandoMensajes ? (
                <div
                  className="space-y-4 py-6"
                  aria-label="Cargando mensajes de la conversación"
                >
                  <div className="flex justify-end">
                    <div className="h-12 w-60 rounded-2xl bg-white/55 dark:bg-white/10 animate-pulse" />
                  </div>
                  <div className="flex items-start gap-3">
                    <div className="h-9 w-9 rounded-full bg-white/55 dark:bg-white/10 animate-pulse" />
                    <div className="h-24 w-96 max-w-full rounded-2xl bg-white/60 dark:bg-white/10 animate-pulse" />
                  </div>
                </div>
              ) : (
                <>
                  {mensajes.map((msg) => (
                    <MessageBubble key={msg.id} mensaje={msg} />
                  ))}
                  {enviando && <FlucitoLoadingBubble actividades={actividades} etapa={etapa} />}
                </>
              )}
            </div>
          </div>

          <div className="mx-auto w-full max-w-3xl pt-1">
            <ChatComposer
              variante="docked"
              deshabilitado={enviando || cargandoMensajes}
              onEnviar={enviarMensaje}
            />
          </div>
        </>
      )}

      {/* Pie informativo */}
      <div className="text-center pt-2">
        <p className="text-[11px] font-medium text-slate-600 dark:text-sky-200/65">
          Flucito puede cometer errores. Verifica la información. • Interflu AI
        </p>
      </div>
    </main>
  );
}
