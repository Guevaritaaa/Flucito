/**
 * Contratos de datos para Chat e Historial de Conversaciones.
 * Espejo 1:1 de backend/app/schemas/chat.py
 */

export interface ReporteHistoricoItem {
  fecha?: string;
  nombre: string;
  id?: string;
  url: string;
}

export interface ActividadChat {
  texto: string;
  estado: "en_curso" | "completado" | "error" | "reintentando" | "recuperado" | "parcial" | "pendiente_verificar";
  id?: string | null;
  tipo?: "modelo" | "funcion" | "accion" | null;
  funcion?: string | null;
  resumen?: string | null;
  resumen_idioma?: "groq" | "original" | null;
}

export interface ChatRequest {
  mensaje: string;
  session_id: string;
  decisiones?: EnvioDecisiones;
}

export interface AvisoReporte { nivel: "advertencia" | "error"; titulo: string; descripcion: string; accion: string }

export interface ChatResponse {
  avisos?: AvisoReporte[];
  respuesta: string;
  sugerir_chat_sae?: boolean;
  interaccion?: InteraccionDecision | null;
  revision_reporte?: RevisionReporte | null;
  archivo_almacen_url: string | null;
  archivo_txt_url: string | null;
  reportes_historicos: ReporteHistoricoItem[];
  actividades?: ActividadChat[];
}

export interface ChatJobCreateResponse {
  job_id: string;
  status: string;
}

export interface ChatJobStatusResponse {
  job_id: string;
  status: "running" | "completed" | "failed" | string;
  result: ChatResponse | null;
  error: string | null;
  etapa?: "pensando" | "trabajando";
  actividades?: ActividadChat[];
  texto_provisional?: string;
}

export interface ConversacionResumenOut {
  id: string;
  usuario_id: number | null;
  titulo: string;
  creada_en: string;
  actualizada_en: string;
  total_mensajes: number;
  tipo?: "general" | "sae";
  bloqueada?: boolean;
}

export interface MensajeChatOut {
  avisos?: AvisoReporte[];
  id: number;
  rol: "user" | "assistant" | string;
  contenido: string;
  sugerir_chat_sae?: boolean;
  interaccion?: InteraccionDecision | null;
  revision_reporte?: RevisionReporte | null;
  archivo_almacen_url: string | null;
  archivo_txt_url: string | null;
  reportes_historicos: ReporteHistoricoItem[];
  creado_en: string;
  actividades?: ActividadChat[];
}

export interface ConversacionDetalleOut {
  id: string;
  usuario_id: number | null;
  titulo: string;
  creada_en: string;
  actualizada_en: string;
  mensajes: MensajeChatOut[];
  tipo?: "general" | "sae";
}

export const CHAT_SAE_BLOQUEADO = "Ya no cuentas con acceso a este chat. Pide acceso a administración para volver a usar Aspel SAE.";
export const ACCESO_SAE_REQUERIDO = "Para usar Aspel SAE, pide acceso a administración.";
export const esIdChatSae = (id: string) => id.startsWith("sae-");

export const PRECIOS_FACTOR = ["PUBLICO", "MINIMO", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR"] as const;
export type PrecioFactor = typeof PRECIOS_FACTOR[number];
export interface PasoFactor { operacion: "*" | "/"; valor: number | string }
export interface FilaFactor { base: "COSTEO" | "PUBLICO"; pasos: PasoFactor[] }
export interface CamposDecision { nombre?: string; precios?: Record<PrecioFactor, FilaFactor>; ruta?: string }
export interface RespuestaDecision { opcion: string; recordar: boolean; campos: CamposDecision }
export interface PreguntaDecision {
  id: string; tipo: string; titulo: string;
  opciones: { id: string; titulo: string; descripcion: string }[];
  contexto: Record<string, string | number | null>;
  explicacion?: string;
  clave_preferencia: string | null; recordada?: boolean; costo_ejemplo?: number;
}
export interface InteraccionDecision {
  id: string; revision: number; estado: "pendiente" | "ejecutando" | "aplicada" | "cancelada" | "error";
  preguntas: PreguntaDecision[]; respuestas: Record<string, RespuestaDecision>;
  permite_recordar: boolean; anteriores?: InteraccionDecision[];
}
export interface EnvioDecisiones {
  interaccion_id: string; revision: number; respuestas: Record<string, RespuestaDecision>;
  accion: "borrador" | "confirmar" | "cancelar";
}
export interface RevisionReporte {
  id: string; version: number; nombre: string; estado: string;
  pendientes: { producto: string; campos: string[] }[];
  relacionados?: RevisionReporte[];
  interaccion?: InteraccionDecision | null;
  resumen_revision?: string;
  factores_pendientes?: { linea: string; descripcion: string }[];
}
