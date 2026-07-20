const API_URL = "http://127.0.0.1:8000/api/v1/chat";
const sessionId = crypto.randomUUID();

const formulario = document.getElementById("formulario-chat");
const entrada = document.getElementById("entrada-mensaje");
const contenedorMensajes = document.getElementById("mensajes");

function agregarMensaje(texto, clase) {
    const div = document.createElement("div");
    div.classList.add("mensaje", clase);
    div.textContent = texto;
    contenedorMensajes.appendChild(div);
    contenedorMensajes.scrollTop = contenedorMensajes.scrollHeight;
    return div;
}

async function enviarMensaje(mensaje) {
    const respuesta = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensaje, session_id: sessionId }),
    });

    if (!respuesta.ok) {
        throw new Error(`Error del servidor: ${respuesta.status}`);
    }

    const datos = await respuesta.json();
    return datos.respuesta;
}

formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    const mensaje = entrada.value.trim();
    if (!mensaje) return;

    agregarMensaje(mensaje, "usuario");
    entrada.value = "";
    entrada.disabled = true;

    const mensajeCargando = agregarMensaje("Flucito está escribiendo...", "cargando");

    try {
        const respuesta = await enviarMensaje(mensaje);
        mensajeCargando.remove();
        agregarMensaje(respuesta, "flucito");
    } catch (error) {
        mensajeCargando.remove();
        agregarMensaje("Hubo un error al contactar a Flucito. Intenta de nuevo.", "flucito");
        console.error(error);
    } finally {
        entrada.disabled = false;
        entrada.focus();
    }
});