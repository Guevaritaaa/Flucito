const host = window.location.hostname;
const BACKEND_URL = host.endsWith("flucito.com")
    ? "https://api.flucito.com"
    : host === "localhost" || host === "127.0.0.1"
        ? "http://127.0.0.1:8000"
        : "";

const API_URL = `${BACKEND_URL}/api/v1/chat`;
const API_DRIVE_UPLOAD_URL = `${BACKEND_URL}/api/v1/almacen/upload`;
const sessionId = globalThis.crypto?.randomUUID?.()
    ?? `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Seleccionamos los elementos de acuerdo al nuevo diseño
const formulario = document.querySelector("form");
const entrada = document.querySelector("textarea");
const contenedorMensajes = document.querySelector('[data-purpose="message-history"]');
const entradaXml = document.getElementById("document-upload");
const estadoXml = document.querySelector('span[title="Estado de archivo"]');
const driveCheckbox = document.getElementById("drive-checkbox");

function despertarBackend() {
    fetch(BACKEND_URL || "/").catch(() => console.log("Despertando backend..."));
}

despertarBackend();

function obtenerHora() {
    return new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
}

function agregarMensaje(texto, clase) {
    const time = obtenerHora();
    let html = "";
    
    // Convertimos de forma segura para evitar inyecciones si no es deseado, o simplemente usamos innerText en un elemento.
    // Para simplificar, insertamos HTML y aplicamos escape o asignamos textContent.
    // Vamos a crear el template de HTML:
    
    if (clase === "usuario") {
        html = `
        <div class="flex flex-col items-end" data-role="user-message">
            <div class="max-w-xl bg-white border border-slate-100 rounded-2xl rounded-tr-sm p-4 shadow-subtle space-y-3">
                <p class="text-sm text-slate-800 leading-relaxed font-normal whitespace-pre-wrap"></p>
            </div>
            <span class="text-[11px] text-slate-400 mt-1 mr-1">${time}</span>
        </div>`;
    } else {
        html = `
        <div class="flex items-start space-x-3" data-role="assistant-message">
            <div class="w-8 h-8 rounded-full overflow-hidden flex items-center justify-center flex-shrink-0 ring-2 ring-cobalt-100 shadow-sm mt-0.5 bg-white">
                <img src="Recursos/FlucitoPerfil.jpeg" alt="Flucito" class="w-full h-full object-cover" />
            </div>
            <div class="max-w-2xl bg-cobalt-700 rounded-2xl rounded-tl-sm p-5 text-white shadow-elevation space-y-3.5">
                <div class="text-sm font-normal leading-relaxed text-blue-50">
                    <p class="whitespace-pre-wrap"></p>
                </div>
            </div>
            <div class="pl-11">
                <span class="text-[11px] text-slate-400">${time} • Flucito</span>
            </div>
        </div>`;
    }

    const template = document.createElement("template");
    template.innerHTML = html.trim();
    const node = template.content.firstChild;
    
    // Inyectar el texto de manera segura
    const parrafo = node.querySelector('p');
    if (parrafo) {
        parrafo.textContent = texto;
    }

    contenedorMensajes.appendChild(node);
    contenedorMensajes.scrollTop = contenedorMensajes.scrollHeight;
    return node;
}

async function enviarMensaje(mensaje) {
    const cuerpo = { mensaje, session_id: sessionId };
    const respuesta = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
    });
    if (!respuesta.ok) throw new Error(`Error del servidor: ${respuesta.status}`);
    return await respuesta.json();
}

agregarMensaje(
    "¡Hola! Soy Flucito, el asistente virtual de Interflu. Ya tengo integrada mi primera herramienta funcional: puedo recibir XML, PDF y TXT, guardarlos en Google Drive por factura, detectar documentos nuevos y generar la base acumulativa de entradas al almacén con un resumen. ¿En qué puedo ayudarte?",
    "flucito"
);

// Eventos de archivos
entradaXml.addEventListener("change", () => {
    const cantidad = entradaXml.files.length;
    const xmls = Array.from(entradaXml.files).filter((archivo) => archivo.name.toLowerCase().endsWith(".xml"));
    
    estadoXml.textContent = cantidad
        ? `${cantidad} documento${cantidad === 1 ? "" : "s"} (${xmls.length} XML)`
        : "Sin archivos seleccionados";
        
    // Subida automática al seleccionar los documentos si se indicó guardarlos.
    if (cantidad > 0 && driveCheckbox.checked) {
        subirDocumentosDrive();
    }
});

async function subirDocumentosDrive() {
    const archivos = Array.from(entradaXml.files);
    if (!archivos.length) return;

    const datos = new FormData();
    archivos.forEach((archivo) => datos.append("archivos", archivo));
    estadoXml.textContent = "Guardando en Drive...";

    try {
        const respuesta = await fetch(API_DRIVE_UPLOAD_URL, { method: "POST", body: datos });
        const resultado = await respuesta.json().catch(() => ({}));
        if (!respuesta.ok) throw new Error(resultado.detail || "Error guardando documentos");
        entradaXml.value = "";
        estadoXml.textContent = `${resultado.subidos} documento${resultado.subidos === 1 ? "" : "s"} guardado${resultado.subidos === 1 ? "" : "s"}.`;
    } catch (error) {
        estadoXml.textContent = error.message || "Error al guardar en Drive";
    }
}

// Soporte para Enter
entrada.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        formulario.requestSubmit();
    }
});

// Manejo de mensajes de chat
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
        
        // Agregar mensaje de respuesta principal
        const msjNode = agregarMensaje(datos.respuesta, "flucito");
        
        let container = msjNode.querySelector('.text-blue-50');
        if (!container) container = msjNode;

        // Descarga de Excel
        if (datos.archivo_almacen_url) {
            const enlace = document.createElement("a");
            enlace.href = new URL(datos.archivo_almacen_url, BACKEND_URL || window.location.origin);
            enlace.download = "BASE_ENTRADAS_ALMACEN.xlsx";
            enlace.innerHTML = "📊 Descargar Excel de almacén";
            enlace.className = "inline-flex items-center px-3 py-1.5 mt-3 mr-2 text-xs font-semibold rounded-lg bg-blue-100 text-cobalt-800 hover:bg-white hover:text-cobalt-900 transition-colors shadow-sm";
            container.appendChild(enlace);
        }

        // Descarga de TXT
        if (datos.archivo_txt_url) {
            const enlaceTxt = document.createElement("a");
            enlaceTxt.href = new URL(datos.archivo_txt_url, BACKEND_URL || window.location.origin);
            enlaceTxt.download = datos.archivo_txt_url.includes("tabs")
                ? "BASE_ENTRADAS_ALMACEN_TABS.txt"
                : "BASE_ENTRADAS_ALMACEN_COMAS.txt";
            enlaceTxt.innerHTML = "📄 Descargar TXT para Aspel";
            enlaceTxt.className = "inline-flex items-center px-3 py-1.5 mt-3 mr-2 text-xs font-semibold rounded-lg bg-emerald-100 text-emerald-800 hover:bg-emerald-50 transition-colors shadow-sm";
            container.appendChild(enlaceTxt);
        }
        
        contenedorMensajes.scrollTop = contenedorMensajes.scrollHeight;
    } catch (error) {
        mensajeCargando.remove();
        agregarMensaje("Hubo un error al contactar a Flucito. Intenta de nuevo.", "flucito");
        console.error(error);
    } finally {
        entrada.disabled = false;
        entrada.focus();
    }
});
