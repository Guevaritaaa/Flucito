import { createRoot } from "react-dom/client";
import "../../src/index.css";
import { ActividadDesplegable } from "../../src/components/chat/ActividadDesplegable";
import { MessageBubble, FlucitoLoadingBubble } from "../../src/components/chat/MessageBubble";
import { useChat } from "../../src/hooks/useChat";
import type { ActividadChat } from "../../src/schemas/chat";

const modo = new URLSearchParams(location.search).get("caso");
if (new URLSearchParams(location.search).has("dark")) document.documentElement.classList.add("dark");
const actividades: ActividadChat[] = [
  { id: "1", tipo: "modelo", texto: "Analizando la solicitud", estado: "completado", resumen: "Revisaré los originales y comprobaré el contenido antes de terminar." },
  { id: "2", tipo: "accion", texto: "Buscando la carpeta", estado: "completado" },
  { id: "3", tipo: "accion", texto: "Restaurando la carpeta", estado: modo === "parcial" ? "parcial" : "completado" },
  { id: "4", tipo: "accion", texto: "Verificando su ubicación", estado: modo === "parcial" ? "pendiente_verificar" : "completado" },
];
if (modo === "error") actividades[2].estado = "error";
if (modo === "recuperado") actividades[0].estado = "recuperado";
function ChatPrueba() {
  const chat = useChat({ sessionId: "prueba-fase4", existeEnHistorial: false, onConversacionActualizada: () => {} });
  return <><button className="rounded-md bg-blue-700 px-4 py-3 text-white" onClick={() => void chat.enviarMensaje("Restablece 17-11-2026")} disabled={chat.enviando}>Enviar solicitud</button>
    <div className="mt-5 space-y-5">{chat.mensajes.map(m => <MessageBubble key={m.id} mensaje={m} />)}
      {chat.enviando && <FlucitoLoadingBubble actividades={chat.actividades} etapa={chat.etapa} textoProvisional={chat.textoProvisional} />}</div></>;
}
createRoot(document.getElementById("root")!).render(<main className="mx-auto min-h-screen max-w-3xl bg-slate-50 p-5 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
  <h1 className="mb-6 text-xl font-semibold">Actividad de Flucito</h1>
  {modo === "live" ? <ChatPrueba /> : modo === "antiguo" ? <MessageBubble mensaje={{ id: "viejo", rol: "assistant", contenido: "Respuesta anterior sin actividad guardada.", hora: "10:00" }} /> : <ActividadDesplegable actividades={actividades} />}
</main>);
