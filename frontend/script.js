const API_URL = "https://flucito.onrender.com/api/v1/chat";
const API_DRIVE_UPLOAD_URL = "https://flucito.onrender.com/api/v1/almacen/upload";
const sessionId = crypto.randomUUID();

const formulario = document.getElementById("formulario-chat");
const entrada = document.getElementById("entrada-mensaje");
const contenedorMensajes = document.getElementById("mensajes");
const entradaXml = document.getElementById("entrada-xml");
const estadoXml = document.getElementById("estado-xml");
const botonSubirDrive = document.getElementById("boton-subir-drive");

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
    const cuerpo = { mensaje, session_id: sessionId };

    const respuesta = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
    });

    if (!respuesta.ok) {
        throw new Error(`Error del servidor: ${respuesta.status}`);
    }

    const datos = await respuesta.json();
    return datos;
}

agregarMensaje(
    "\u00a1Hola! Soy Flucito, el asistente virtual de Interflu. Ya tengo integrada mi primera herramienta funcional: puedo recibir XML, PDF y TXT, guardarlos en Google Drive por factura, detectar documentos nuevos y generar la base acumulativa de entradas al almacén con un resumen. \u00bfEn qué puedo ayudarte?",
    "flucito"
);

entradaXml.addEventListener("change", () => {
    const cantidad = entradaXml.files.length;
    const xmls = Array.from(entradaXml.files).filter((archivo) => archivo.name.toLowerCase().endsWith(".xml"));
    botonSubirDrive.disabled = cantidad === 0;
    estadoXml.textContent = cantidad
        ? `${cantidad} documento${cantidad === 1 ? "" : "s"} seleccionado${cantidad === 1 ? "" : "s"} (${xmls.length} XML)`
        : "Sin archivos seleccionados";
});

async function subirDocumentosDrive() {
    const archivos = Array.from(entradaXml.files);
    if (!archivos.length) return;

    const datos = new FormData();
    archivos.forEach((archivo) => datos.append("archivos", archivo));
    botonSubirDrive.disabled = true;
    estadoXml.textContent = "Guardando documentos en Drive...";

    try {
        const respuesta = await fetch(API_DRIVE_UPLOAD_URL, { method: "POST", body: datos });
        const resultado = await respuesta.json().catch(() => ({}));
        if (!respuesta.ok) throw new Error(resultado.detail || "No se pudieron guardar documentos en Drive");
        entradaXml.value = "";
        estadoXml.textContent = `${resultado.subidos} documento${resultado.subidos === 1 ? "" : "s"} nuevo${resultado.subidos === 1 ? "" : "s"} guardado${resultado.subidos === 1 ? "" : "s"} en Drive.`;
    } catch (error) {
        estadoXml.textContent = error.message || "Error al guardar en Drive";
        botonSubirDrive.disabled = false;
    }
}

botonSubirDrive.addEventListener("click", subirDocumentosDrive);

formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();

    const mensaje = entrada.value.trim();
    if (!mensaje) return;

    agregarMensaje(mensaje, "usuario");
    entrada.value = "";
    entrada.disabled = true;

    const mensajeCargando = agregarMensaje("Flucito está escribiendo...", "cargando");

    try {
        const datos = await enviarMensaje(mensaje);
        mensajeCargando.remove();
        agregarMensaje(datos.respuesta, "flucito");
        const archivoUrl = datos.archivo_almacen_url;
        if (archivoUrl) {
            const enlace = document.createElement("a");
            enlace.href = new URL(archivoUrl, BACKEND_URL);
            enlace.download = "BASE_ENTRADAS_ALMACEN.xlsx";
            enlace.textContent = "Descargar base de almacén";
            enlace.className = "enlace-descarga";
            contenedorMensajes.appendChild(enlace);
            contenedorMensajes.scrollTop = contenedorMensajes.scrollHeight;
        }
    } catch (error) {
        mensajeCargando.remove();
        agregarMensaje("Hubo un error al contactar a Flucito. Intenta de nuevo.", "flucito");
        console.error(error);
    } finally {
        entrada.disabled = false;
        entrada.focus();
    }
});
