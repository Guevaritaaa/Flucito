import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  guardarToken,
  guardarUsuario,
  limpiarSesionGuardada,
  obtenerTokenGuardado,
  obtenerUsuarioGuardado,
} from "../core/storage";
import type { LoginRequest, UsuarioOut } from "../schemas/auth";
import { iniciarSesion, obtenerPerfilActual } from "../services/authService";
import { despertarBackend, registrarManejadorNoAutorizado } from "../services/http";

export interface AuthContextValue {
  usuario: UsuarioOut | null;
  token: string | null;
  autenticado: boolean;
  esAdmin: boolean;
  cargandoSesion: boolean;
  login: (credenciales: LoginRequest) => Promise<UsuarioOut>;
  logout: () => void;
  recargarPerfil: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => obtenerTokenGuardado());
  const [usuario, setUsuario] = useState<UsuarioOut | null>(() => obtenerUsuarioGuardado());
  const [cargandoSesion, setCargandoSesion] = useState<boolean>(() => Boolean(obtenerTokenGuardado()));

  const logout = useCallback(() => {
    limpiarSesionGuardada();
    setToken(null);
    setUsuario(null);
    setCargandoSesion(false);
  }, []);

  useEffect(() => {
    despertarBackend();
    registrarManejadorNoAutorizado(() => {
      logout();
    });
    return () => {
      registrarManejadorNoAutorizado(null);
    };
  }, [logout]);

  const recargarPerfil = useCallback(async () => {
    const tokenActual = obtenerTokenGuardado();
    if (!tokenActual) {
      logout();
      return;
    }
    try {
      const perfil = await obtenerPerfilActual();
      guardarUsuario(perfil);
      setUsuario(perfil);
    } catch {
      logout();
    } finally {
      setCargandoSesion(false);
    }
  }, [logout]);

  useEffect(() => {
    if (token) {
      void recargarPerfil();
    } else {
      setCargandoSesion(false);
    }
  }, [token, recargarPerfil]);

  const login = useCallback(async (credenciales: LoginRequest): Promise<UsuarioOut> => {
    const respuesta = await iniciarSesion(credenciales);
    guardarToken(respuesta.access_token);
    guardarUsuario(respuesta.usuario);
    setToken(respuesta.access_token);
    setUsuario(respuesta.usuario);
    return respuesta.usuario;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      usuario,
      token,
      autenticado: Boolean(token && usuario),
      esAdmin: usuario?.rol === "admin",
      cargandoSesion,
      login,
      logout,
      recargarPerfil,
    }),
    [usuario, token, cargandoSesion, login, logout, recargarPerfil]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth debe utilizarse dentro de un <AuthProvider>");
  }
  return context;
}
