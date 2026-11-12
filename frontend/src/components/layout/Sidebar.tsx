import { useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Home,
  LogOut,
  MessageSquare,
  MessageSquarePlus,
  RefreshCw,
  Settings,
  Shield,
  Trash2,
  User as UserIcon,
  X,
} from "lucide-react";
import { ASSETS } from "../../core/config";
import type { UsuarioOut } from "../../schemas/auth";
import type { ConversacionResumenOut } from "../../schemas/chat";

export type AppTab = "inicio" | "chat" | "configuracion";

interface SidebarProps {
  abierto: boolean;
  onToggle: () => void;
  tabActiva: AppTab;
  onSelectTab: (tab: AppTab) => void;
  usuario: UsuarioOut;
  onLogout: () => void;
  conversaciones: ConversacionResumenOut[];
  sessionIdActivo: string;
  cargandoHistorial: boolean;
  onNuevaConversacion: () => void;
  onSeleccionarConversacion: (sessionId: string) => void;
  onBorrarConversacion: (sessionId: string) => Promise<void>;
  onRefrescarHistorial: () => void;
}

function formatearFechaRelativa(isoDate: string): string {
  try {
    const fecha = new Date(isoDate);
    const ahora = new Date();
    const diffDias = Math.floor(
      (ahora.setHours(0, 0, 0, 0) - new Date(fecha).setHours(0, 0, 0, 0)) /
        (1000 * 60 * 60 * 24)
    );
    if (diffDias <= 0) {
      return fecha.toLocaleTimeString("es-MX", {
        hour: "2-digit",
        minute: "2-digit",
      });
    }
    if (diffDias === 1) return "Ayer";
    return fecha.toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
    });
  } catch {
    return "";
  }
}

export function Sidebar({
  abierto,
  onToggle,
  tabActiva,
  onSelectTab,
  usuario,
  onLogout,
  conversaciones,
  sessionIdActivo,
  cargandoHistorial,
  onNuevaConversacion,
  onSeleccionarConversacion,
  onBorrarConversacion,
  onRefrescarHistorial,
}: SidebarProps) {
  const [confirmandoBorradoId, setConfirmandoBorradoId] = useState<string | null>(
    null
  );
  const [borrandoId, setBorrandoId] = useState<string | null>(null);

  const navItems: { id: AppTab; label: string; icon: typeof Home }[] = [
    { id: "inicio", label: "Inicio", icon: Home },
    { id: "chat", label: "Chat", icon: MessageSquare },
    { id: "configuracion", label: "Configuración", icon: Settings },
  ];

  async function confirmarEliminacion(sessionId: string) {
    setBorrandoId(sessionId);
    try {
      await onBorrarConversacion(sessionId);
    } finally {
      setBorrandoId(null);
      setConfirmandoBorradoId(null);
    }
  }

  return (
    <>
      {/* Fondo oscuro traslúcido en móvil cuando el sidebar está abierto */}
      {abierto && (
        <div
          onClick={onToggle}
          aria-hidden="true"
          className="fixed inset-0 z-30 bg-slate-950/40 backdrop-blur-[1px] md:hidden transition-opacity"
        />
      )}

      <aside
        id="sidebar"
        style={{
          marginLeft: abierto ? "0rem" : "-16rem",
          transition: "margin-left 240ms cubic-bezier(0.32, 0.72, 0, 1)",
        }}
        className="fixed md:relative z-40 flex h-full w-64 flex-shrink-0 flex-col justify-between bg-[#0018CC] dark:bg-dark-sidebar border-r border-[#0014a8] dark:border-cobalt-900/80 text-white select-none shadow-2xl md:shadow-none"
      >
        {/* Bloque Superior: Logo + Nueva Conversación + Navegación Principal */}
        <div className="flex flex-col p-4 pb-2 space-y-4">
          {/* Logotipo Interflu en contenedor translúcido del prototipo */}
          <div className="flex items-center pt-0.5">
            <div className="w-full flex items-center justify-center rounded-xl border border-white/30 bg-white/10 p-2 backdrop-blur-xs">
              <img
                src={ASSETS.INTERFLU_LOGO}
                alt="Interflu Logo"
                className="w-full h-auto max-h-12 object-contain"
              />
            </div>
          </div>

          {/* Acción Primaria: Nueva Conversación */}
          <button
            type="button"
            onClick={() => {
              onNuevaConversacion();
              onSelectTab("chat");
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/25 bg-white/12 hover:bg-white/20 active:scale-[0.98] px-3.5 py-2.5 text-xs font-semibold text-white shadow-sm transition-all duration-150 cursor-pointer"
          >
            <MessageSquarePlus className="h-4 w-4 text-blue-100" />
            <span>Nueva conversación</span>
          </button>

          {/* Navegación de 3 pestañas (Inicio, Chat, Configuración) */}
          <nav className="space-y-1" aria-label="Navegación principal">
            {navItems.map((item) => {
              const Icon = item.icon;
              const activo = tabActiva === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectTab(item.id)}
                  className={`group flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-left text-sm transition-all duration-150 active:scale-[0.99] cursor-pointer ${
                    activo
                      ? "bg-[#0070F3] font-semibold text-white shadow-sm"
                      : "font-medium text-blue-100 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 flex-shrink-0 ${
                      activo
                        ? "text-white"
                        : "text-blue-200 group-hover:text-white"
                    }`}
                  />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bloque Central: Historial de Conversaciones del Usuario */}
        <div className="flex flex-1 flex-col overflow-hidden px-4 py-2 border-t border-blue-800/50">
          <div className="flex items-center justify-between px-1.5 py-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-blue-200/80">
              Tus conversaciones ({conversaciones.length})
            </span>
            <button
              type="button"
              onClick={onRefrescarHistorial}
              title="Actualizar historial"
              aria-label="Actualizar historial de conversaciones"
              className="rounded-md p-1 text-blue-200/80 hover:bg-white/10 hover:text-white transition-colors cursor-pointer"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${cargandoHistorial ? "animate-spin" : ""}`}
              />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto sidebar-scroll space-y-1 pr-1 mt-1">
            {cargandoHistorial && conversaciones.length === 0 ? (
              <div className="space-y-2 py-2 px-1" aria-label="Cargando conversaciones">
                <div className="h-9 rounded-lg bg-white/10 animate-pulse" />
                <div className="h-9 rounded-lg bg-white/10 animate-pulse" />
                <div className="h-9 rounded-lg bg-white/10 animate-pulse" />
              </div>
            ) : conversaciones.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/5 p-3.5 text-left space-y-1 my-1">
                <p className="text-xs font-medium text-blue-100">
                  Sin conversaciones guardadas
                </p>
                <p className="text-[11px] text-blue-200/75 leading-relaxed">
                  Escribe un mensaje a Flucito y tu sesión se guardará automáticamente aquí.
                </p>
              </div>
            ) : (
              conversaciones.map((conv) => {
                const esActiva =
                  conv.id === sessionIdActivo && tabActiva === "chat";
                const confirmando = confirmandoBorradoId === conv.id;
                const borrando = borrandoId === conv.id;

                return (
                  <div
                    key={conv.id}
                    className={`group relative flex items-center justify-between rounded-xl px-2.5 py-2 text-xs transition-colors duration-150 ${
                      esActiva
                        ? "bg-white/18 text-white font-semibold shadow-2xs ring-1 ring-white/25"
                        : "text-blue-100 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    {confirmando ? (
                      <div className="flex w-full items-center justify-between gap-1.5 py-0.5">
                        <span className="truncate text-[11px] font-medium text-amber-200">
                          ¿Eliminar este chat?
                        </span>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            type="button"
                            disabled={borrando}
                            onClick={() => void confirmarEliminacion(conv.id)}
                            className="inline-flex items-center gap-1 rounded-md bg-red-500/90 hover:bg-red-500 px-2 py-1 text-[11px] font-semibold text-white transition-colors cursor-pointer"
                            title="Confirmar eliminación"
                          >
                            <Check className="h-3 w-3" />
                            <span>Sí</span>
                          </button>
                          <button
                            type="button"
                            disabled={borrando}
                            onClick={() => setConfirmandoBorradoId(null)}
                            className="inline-flex items-center rounded-md bg-white/15 hover:bg-white/25 p-1 text-white transition-colors cursor-pointer"
                            title="Cancelar"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            onSeleccionarConversacion(conv.id);
                            onSelectTab("chat");
                          }}
                          className="flex flex-1 flex-col items-start overflow-hidden pr-2 text-left cursor-pointer"
                          title={conv.titulo}
                        >
                          <span className="w-full truncate leading-snug">
                            {conv.titulo || "Conversación sin título"}
                          </span>
                          <span className="text-[10px] text-blue-200/75 font-normal mt-0.5">
                            {formatearFechaRelativa(conv.actualizada_en)} •{" "}
                            {conv.total_mensajes}{" "}
                            {conv.total_mensajes === 1 ? "msj" : "msjs"}
                          </span>
                        </button>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmandoBorradoId(conv.id);
                          }}
                          aria-label={`Eliminar conversación ${conv.titulo}`}
                          title="Eliminar conversación"
                          className="opacity-0 group-hover:opacity-100 focus:opacity-100 rounded-lg p-1.5 text-blue-200 hover:bg-red-500/25 hover:text-red-200 transition-all cursor-pointer flex-shrink-0"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Bloque Inferior: Perfil del Usuario Autenticado + Cerrar Sesión */}
        <div className="p-3.5 border-t border-blue-800/60 bg-[#0014a8]/40 dark:bg-slate-950/40">
          <div className="flex items-center justify-between gap-2 rounded-xl px-2 py-1.5">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="h-8 w-8 flex-shrink-0 rounded-full bg-white/20 flex items-center justify-center text-white ring-1 ring-white/30">
                {usuario.rol === "admin" ? (
                  <Shield className="h-4 w-4 text-amber-300" />
                ) : (
                  <UserIcon className="h-4 w-4 text-blue-100" />
                )}
              </div>
              <div className="truncate">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-white truncate">
                    {usuario.nombre_completo}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="text-[10px] text-blue-200 truncate">
                    @{usuario.username}
                  </span>
                  <span className="inline-flex items-center rounded bg-white/15 px-1.5 py-0.2 text-[9px] font-semibold uppercase tracking-wide text-blue-100">
                    {usuario.rol}
                  </span>
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={onLogout}
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
              className="rounded-lg p-2 text-blue-200 hover:bg-white/15 hover:text-white active:scale-95 transition-all cursor-pointer flex-shrink-0"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Botón de media luna del prototipo para colapsar/expandir el Sidebar */}
        <button
          type="button"
          onClick={onToggle}
          aria-label={abierto ? "Ocultar barra lateral" : "Mostrar barra lateral"}
          title={abierto ? "Ocultar menú lateral" : "Mostrar menú lateral"}
          className="absolute -right-5 top-1/2 -translate-y-1/2 z-50 flex h-12 w-5 items-center justify-center rounded-r-full bg-[#0018CC] dark:bg-dark-sidebar hover:bg-[#1a3fd8] dark:hover:bg-cobalt-800 border-y border-r border-[#0014a8] dark:border-cobalt-800 text-blue-300 hover:text-white transition-colors cursor-pointer"
        >
          {abierto ? (
            <ChevronLeft className="h-3.5 w-3.5 stroke-[2.5]" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 stroke-[2.5]" />
          )}
        </button>
      </aside>
    </>
  );
}
