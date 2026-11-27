/**
 * Contratos de datos para Autenticación y Usuarios.
 * Espejo 1:1 de backend/app/schemas/auth.py
 */

export type RolUsuario = "admin" | "operador";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface UsuarioOut {
  id: number;
  username: string;
  nombre_completo: string;
  rol: RolUsuario | string;
  activo: boolean;
  acceso_sae: boolean;
  creado_en: string;
  ultimo_login: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  usuario: UsuarioOut;
}

export interface UsuarioCreateRequest {
  username: string;
  nombre_completo: string;
  password: string;
  rol?: RolUsuario;
}

export interface UsuarioUpdateRequest {
  nombre_completo?: string;
  password?: string;
  rol?: RolUsuario;
  activo?: boolean;
  acceso_sae?: boolean;
}
