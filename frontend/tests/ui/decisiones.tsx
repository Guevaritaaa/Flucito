import { mensajeVigente } from "../../src/components/chat/mensajeVigente";
import { createRoot } from "react-dom/client";
import "../../src/index.css";
import { useChat } from "../../src/hooks/useChat";
import { MessageBubble } from "../../src/components/chat/MessageBubble";

if (new URLSearchParams(location.search).has("dark")) document.documentElement.classList.add("dark");
function Prueba() {
  const chat = useChat({ sessionId: "decision-e2e", existeEnHistorial: true, onConversacionActualizada: () => {} });
  return <main className="mx-auto min-h-screen max-w-3xl space-y-5 bg-slate-50 p-4 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
    <h1 className="text-xl font-semibold">Revisión de entradas de almacén</h1>
    {chat.mensajes.map((m, index) => <MessageBubble key={m.id} mensaje={mensajeVigente(m, chat.mensajes.slice(index + 1))} sessionId="decision-e2e" onDecision={chat.enviarMensaje} ocupado={chat.enviando} />)}
  </main>;
}
createRoot(document.getElementById("root")!).render(<Prueba />);
