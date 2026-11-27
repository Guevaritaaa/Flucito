/**
 * Servicio de Autenticación JWT y Administración de Usuarios.
 * Consume /api/v1/auth/* (backend/app/api/v1/routes/auth.py)
 */

import type {
  LoginRequest,
  TokenResponse,
  UsuarioCreateRequest,
  UsuarioOut,
  UsuarioUpdateRequest,
} from "../schemas/auth";
import { apiFetch } from "./http";

export async function iniciarSesion(credenciales: LoginRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: credenciales,
    skipAuth: true,
    skipUnauthorizedHook: true,
  });
}

export async function obtenerPerfilActual(): Promise<UsuarioOut> {
  return apiFetch<UsuarioOut>("/auth/me", {
    method: "GET",
    cache: "no-store",
  });
}

export async function listarUsuarios(): Promise<UsuarioOut[]> {
  return apiFetch<UsuarioOut[]>("/auth/usuarios", {
    method: "GET",
  });
}

export async function crearUsuario(payload: UsuarioCreateRequest): Promise<UsuarioOut> {
  return apiFetch<UsuarioOut>("/auth/usuarios", {
    method: "POST",
    body: payload,
  });
}

export async function actualizarUsuario(
  usuarioId: number,
  payload: UsuarioUpdateRequest
): Promise<UsuarioOut> {
  return apiFetch<UsuarioOut>(`/auth/usuarios/${usuarioId}`, {
    method: "PATCH",
    body: payload,
  });
}
