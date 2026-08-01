const API_URL = "https://flucito.onrender.com/api/v1/chat";
const API_CFDI_URL = "https://flucito.onrender.com/api/v1/cfdi/excel";
const sessionId = crypto.randomUUID();

const formulario = document.getElementById("formulario-chat");
const entrada = document.getElementById("entrada-mensaje");
const contenedorMensajes = document.getElementById("mensajes");
const entradaXml = document.getElementById("entrada-xml");
const estadoXml = document.getElementById("estado-xml");
const botonGenerarExcel = document.getElementById("boton-generar-excel");

const BACKEND_URL = "https://flucito.onrender.com";

function despertarBackend() {
    const estado = document.getElementById("estado-backend");
    fetch(BACKEND_URL)
        .then(() => {
            if (estado) estado.remove();
        })
        .catch(() => {
            if (estado) estado.textContent = "El servidor está despertando, dale un momento...";
        });
}

despertarBackend();

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

agregarMensaje(
    "¡Hola! Soy Flucito, el asistente virtual de Interflu. ¿En qué puedo ayudarte?",
    "flucito"
);

entradaXml.addEventListener("change", () => {
    const cantidad = entradaXml.files.length;
    botonGenerarExcel.disabled = cantidad === 0;
    estadoXml.textContent = cantidad
        ? `${cantidad} archivo${cantidad === 1 ? "" : "s"} XML seleccionado${cantidad === 1 ? "" : "s"}`
        : "Sin archivos seleccionados";
});

async function generarExcelDesdeXml() {
    const archivos = Array.from(entradaXml.files);
    if (!archivos.length) return;

    const datos = new FormData();
    archivos.forEach((archivo) => datos.append("archivos", archivo));
    botonGenerarExcel.disabled = true;
    estadoXml.textContent = "Generando Excel...";

    try {
        const respuesta = await fetch(API_CFDI_URL, {
            method: "POST",
            body: datos,
        });

        if (!respuesta.ok) {
            const error = await respuesta.json().catch(() => ({}));
            throw new Error(error.detail || "No se pudo generar el Excel");
        }

        const archivoExcel = await respuesta.blob();
        const url = URL.createObjectURL(archivoExcel);
        const enlace = document.createElement("a");
        enlace.href = url;
        enlace.download = "reporte_cfdi.xlsx";
        enlace.click();
        URL.revokeObjectURL(url);

        entradaXml.value = "";
        estadoXml.textContent = "Excel descargado";
    } catch (error) {
        estadoXml.textContent = error.message || "Error al generar Excel";
        botonGenerarExcel.disabled = false;
    }
}

botonGenerarExcel.addEventListener("click", generarExcelDesdeXml);

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
