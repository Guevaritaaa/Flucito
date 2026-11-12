/**
 * Utilidades de almacenamiento local para sesión JWT y conversación activa.
 */

import {
  ACTIVE_SESSION_STORAGE_KEY,
  AUTH_TOKEN_STORAGE_KEY,
  AUTH_USER_STORAGE_KEY,
} from "./config";
import type { UsuarioOut } from "../schemas/auth";

export function obtenerTokenGuardado(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function guardarToken(token: string): void {
  try {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignorar errores de cuota o modo privado restringido
  }
}

export function obtenerUsuarioGuardado(): UsuarioOut | null {
  try {
    const raw = localStorage.getItem(AUTH_USER_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UsuarioOut;
  } catch {
    return null;
  }
}

export function guardarUsuario(usuario: UsuarioOut): void {
  try {
    localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(usuario));
  } catch {
    // Ignorar errores de almacenamiento
  }
}

export function limpiarSesionGuardada(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    localStorage.removeItem(AUTH_USER_STORAGE_KEY);
  } catch {
    // Ignorar
  }
}

export function generarNuevoSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function obtenerSessionIdActivo(): string {
  try {
    const guardado = localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
    if (guardado && guardado.trim().length > 0) {
      return guardado;
    }
  } catch {
    // Ignorar
  }
  const nuevo = generarNuevoSessionId();
  guardarSessionIdActivo(nuevo);
  return nuevo;
}

export function guardarSessionIdActivo(sessionId: string): void {
  try {
    localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
  } catch {
    // Ignorar
  }
}
