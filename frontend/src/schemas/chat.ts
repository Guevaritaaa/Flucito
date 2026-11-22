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
  estado: "en_curso" | "completado" | "error" | "reintentando" | "recuperado";
  id?: string | null;
  tipo?: "modelo" | "funcion" | null;
  funcion?: string | null;
}

export interface ChatRequest {
  mensaje: string;
  session_id: string;
}

export interface ChatResponse {
  respuesta: string;
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
}

export interface MensajeChatOut {
  id: number;
  rol: "user" | "assistant" | string;
  contenido: string;
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
}
