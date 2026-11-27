import { useState } from "react";
import {
  Check,
  ChartColumn,
  Home,
  LogOut,
  LockKeyhole,
  MessageSquare,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
  User as UserIcon,
  X,
} from "lucide-react";
import { useTheme } from "../../context/ThemeContext";
import { ASSETS } from "../../core/config";
import type { UsuarioOut } from "../../schemas/auth";
import { CHAT_SAE_BLOQUEADO, type ConversacionResumenOut } from "../../schemas/chat";
import { AccionSae } from "../chat/AccionSae";

export type AppTab = "inicio" | "chat" | "configuracion" | "sae";

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
  onAbrirChatSae: () => void;
  creandoSae: boolean;
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
  onAbrirChatSae,
  creandoSae,
  onSeleccionarConversacion,
  onBorrarConversacion,
  onRefrescarHistorial,
}: SidebarProps) {
  const { esOscuro } = useTheme();
  const [confirmandoBorradoId, setConfirmandoBorradoId] = useState<string | null>(
    null
  );
  const [borrandoId, setBorrandoId] = useState<string | null>(null);

  const navItems: { id: AppTab; label: string; icon: typeof Home }[] = [
    { id: "inicio", label: "Inicio", icon: Home },
    { id: "chat", label: "Chat", icon: MessageSquare },
    { id: "configuracion", label: "Configuración", icon: Settings },
  ];

  function cerrarEnMovil() {
    if (typeof window !== "undefined" && window.innerWidth < 768 && abierto) {
      onToggle();
    }
  }

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
      {/* Velo translúcido en móvil cuando el panel lateral está desplegado */}
      {abierto && (
        <div
          onClick={onToggle}
          aria-hidden="true"
          className="fixed inset-0 z-30 bg-slate-950/35 backdrop-blur-[2px] md:hidden transition-opacity"
        />
      )}

      <aside
        id="sidebar"
        aria-label="Barra lateral de navegación e historial"
        inert={!abierto}
        className={`absolute inset-y-0 left-0 md:relative z-40 flex h-full w-[268px] max-w-full flex-shrink-0 flex-col overflow-auto overscroll-contain sidebar-scroll border-r border-white/65 dark:border-sky-200/15 bg-white/55 dark:bg-[#081530]/78 backdrop-blur-2xl text-slate-800 dark:text-slate-100 select-none shadow-[12px_0_36px_rgba(12,50,110,0.12)] md:shadow-none transition-[translate,margin-left] duration-[240ms] ease-[cubic-bezier(0.32,0.72,0,1)] ${
          abierto ? "" : "-translate-x-full md:translate-x-0 md:-ml-[268px]"
        }`}
      >
        {/* Cabecera estilo ChatGPT: Logo Interflu + botón discreto de colapsar */}
        <div className="flex shrink-0 flex-col px-3.5 pt-4 pb-2.5 space-y-3.5">
          <div className="flex items-center justify-between gap-2 px-1">
            <img
              src={esOscuro ? ASSETS.INTERFLU_LOGO_DARK : ASSETS.INTERFLU_LOGO}
              alt="Interflu - Internacional de Fluidos, S.A. de C.V."
              className="w-[148px] h-auto object-contain select-none"
            />

            <button
              type="button"
              onClick={onToggle}
              aria-label="Ocultar barra lateral"
              title="Ocultar barra lateral"
              className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl text-slate-600 dark:text-sky-200/80 hover:bg-white/65 dark:hover:bg-sky-400/15 hover:text-slate-900 dark:hover:text-white active:scale-[0.96] transition-all duration-150 cursor-pointer"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </div>

          {/* Botón Primario: + Nuevo chat (cápsula blanca elevada en claro / cristal celeste en oscuro) */}
          <button
            type="button"
            onClick={() => {
              onNuevaConversacion();
              onSelectTab("chat");
              cerrarEnMovil();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/90 dark:border-sky-300/25 bg-white/92 hover:bg-white dark:bg-[#10254c]/85 dark:hover:bg-[#163266]/95 active:scale-[0.98] px-4 py-2.5 text-xs sm:text-[13px] font-bold text-slate-900 dark:text-white shadow-[0_6px_18px_rgba(12,50,110,0.08)] dark:shadow-[0_8px_20px_rgba(2,8,24,0.45)] transition-all duration-150 cursor-pointer"
          >
            <Plus className="h-4 w-4 stroke-[2.4] text-[#0022e6] dark:text-sky-300" />
            <span>Nuevo chat</span>
          </button>

          {/* Navegación principal */}
          <nav className="space-y-0.5 pt-0.5" aria-label="Navegación principal">
            {navItems.map((item) => {
              const Icon = item.icon;
              const activo = tabActiva === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onSelectTab(item.id);
                    cerrarEnMovil();
                  }}
                  className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[13px] transition-all duration-150 active:scale-[0.99] cursor-pointer ${
                    activo
                      ? "bg-[#0022e6]/11 dark:bg-sky-400/18 font-semibold text-[#0018cc] dark:text-white"
                      : "font-medium text-slate-700 dark:text-sky-100/80 hover:bg-white/55 dark:hover:bg-white/8 hover:text-slate-950 dark:hover:text-white"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 flex-shrink-0 transition-colors ${
                      activo
                        ? "text-[#0022e6] dark:text-sky-300"
                        : "text-slate-500 dark:text-sky-200/70 group-hover:text-slate-800 dark:group-hover:text-white"
                    }`}
                  />
                  <span>{item.label}</span>
                </button>
              );
            })}
            <AccionSae
              permitido={usuario.acceso_sae === true}
              paginaActual={tabActiva === "sae" && usuario.acceso_sae}
              onClick={() => { onSelectTab("sae"); cerrarEnMovil(); }}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[13px] font-medium ${
                tabActiva === "sae" && usuario.acceso_sae
                  ? "bg-[#0022e6]/11 font-semibold text-[#0018cc] dark:bg-sky-400/18 dark:text-white"
                  : "hover:bg-white/55 dark:hover:bg-white/8"
              }`}
            >
              <ChartColumn className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Aspel SAE</span>
            </AccionSae>
            <AccionSae
              permitido={usuario.acceso_sae === true}
              ocupado={creandoSae}
              onClick={onAbrirChatSae}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[13px] font-medium hover:bg-white/55 dark:hover:bg-white/8"
            >
              <MessageSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Abrir chat SAE</span>
            </AccionSae>
          </nav>
        </div>

        {/* Bloque Central: Chats recientes */}
        <div className="flex flex-1 min-h-24 flex-col overflow-hidden px-3.5 py-2 border-t border-slate-900/7 dark:border-sky-200/10">
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-xs font-bold text-slate-700 dark:text-sky-100/85">
              Chats recientes
              {conversaciones.length > 0 ? ` (${conversaciones.length})` : ""}
            </span>
            <button
              type="button"
              onClick={onRefrescarHistorial}
              title="Actualizar historial"
              aria-label="Actualizar historial de conversaciones"
              className="rounded-lg p-1 text-slate-500 dark:text-sky-200/70 hover:bg-white/60 dark:hover:bg-white/10 hover:text-slate-800 dark:hover:text-white transition-colors cursor-pointer"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${cargandoHistorial ? "animate-spin" : ""}`}
              />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto sidebar-scroll space-y-0.5 pr-1 mt-0.5">
            {cargandoHistorial && conversaciones.length === 0 ? (
              <div className="space-y-1.5 py-2 px-1" aria-label="Cargando conversaciones">
                <div className="h-9 rounded-xl bg-white/50 dark:bg-white/8 animate-pulse" />
                <div className="h-9 rounded-xl bg-white/50 dark:bg-white/8 animate-pulse" />
                <div className="h-9 rounded-xl bg-white/50 dark:bg-white/8 animate-pulse" />
              </div>
            ) : conversaciones.length === 0 ? (
              <div className="rounded-2xl bg-white/45 dark:bg-white/5 px-3.5 py-3 text-left space-y-1 my-1">
                <p className="text-xs font-semibold text-slate-700 dark:text-sky-100">
                  Sin chats recientes
                </p>
                <p className="text-[11px] text-slate-600 dark:text-sky-200/70 leading-relaxed">
                  Envía un mensaje a Flucito y tu conversación aparecerá aquí automáticamente.
                </p>
              </div>
            ) : (
              conversaciones.map((conv) => {
                if (conv.tipo === "sae" && (conv.bloqueada || !usuario.acceso_sae)) {
                  return (
                    <button
                      key={conv.id}
                      type="button"
                      aria-disabled="true"
                      title={CHAT_SAE_BLOQUEADO}
                      onClick={() => { onSeleccionarConversacion(conv.id); cerrarEnMovil(); }}
                      className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-xs text-slate-600 dark:text-slate-400 cursor-not-allowed"
                    >
                      <LockKeyhole className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /> Chat de Aspel SAE
                    </button>
                  );
                }
                const esActiva =
                  conv.id === sessionIdActivo && tabActiva === "chat";
                const confirmando = confirmandoBorradoId === conv.id;
                const borrando = borrandoId === conv.id;

                return (
                  <div
                    key={conv.id}
                    className={`group relative flex items-center justify-between rounded-xl px-2.5 py-2 text-xs transition-colors duration-150 ${
                      esActiva
                        ? "bg-[#0022e6]/12 dark:bg-sky-400/20 text-slate-950 dark:text-white font-semibold"
                        : "text-slate-700 dark:text-sky-100/80 hover:bg-white/55 dark:hover:bg-white/8 hover:text-slate-950 dark:hover:text-white"
                    }`}
                  >
                    {confirmando ? (
                      <div className="flex w-full items-center justify-between gap-1.5 py-0.5">
                        <span className="truncate text-[11px] font-semibold text-red-700 dark:text-amber-200">
                          ¿Eliminar chat?
                        </span>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            type="button"
                            disabled={borrando}
                            onClick={() => void confirmarEliminacion(conv.id)}
                            className="inline-flex items-center gap-1 rounded-lg bg-red-600 hover:bg-red-700 px-2 py-1 text-[11px] font-semibold text-white transition-colors cursor-pointer"
                            title="Confirmar eliminación"
                          >
                            <Check className="h-3 w-3" />
                            <span>Sí</span>
                          </button>
                          <button
                            type="button"
                            disabled={borrando}
                            onClick={() => setConfirmandoBorradoId(null)}
                            className="inline-flex items-center rounded-lg bg-slate-900/10 dark:bg-white/15 hover:bg-slate-900/18 dark:hover:bg-white/25 p-1 text-slate-700 dark:text-white transition-colors cursor-pointer"
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
                            cerrarEnMovil();
                          }}
                          className="flex flex-1 items-start gap-2.5 overflow-hidden pr-1.5 text-left cursor-pointer"
                          title={conv.titulo}
                        >
                          <MessageSquare
                            className={`mt-0.5 h-3.5 w-3.5 flex-shrink-0 ${
                              esActiva
                                ? "text-[#0022e6] dark:text-sky-300"
                                : "text-slate-500 dark:text-sky-200/60"
                            }`}
                          />
                          <div className="min-w-0 flex-1">
                            <span className="block w-full truncate leading-snug">
                              {conv.titulo || "Conversación sin título"}
                            </span>
                            <span className="block text-[10px] text-slate-500 dark:text-sky-200/65 font-normal mt-0.5">
                              {formatearFechaRelativa(conv.actualizada_en)} •{" "}
                              {conv.total_mensajes}{" "}
                              {conv.total_mensajes === 1 ? "msj" : "msjs"}
                            </span>
                          </div>
                        </button>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmandoBorradoId(conv.id);
                          }}
                          aria-label={`Eliminar conversación ${conv.titulo}`}
                          title="Eliminar conversación"
                          className="opacity-0 group-hover:opacity-100 focus:opacity-100 rounded-lg p-1.5 text-slate-500 dark:text-sky-200/70 hover:bg-red-500/15 hover:text-red-700 dark:hover:bg-red-500/25 dark:hover:text-red-200 transition-all cursor-pointer flex-shrink-0"
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

        {/* Pie de Perfil: Tarjeta de cristal esmerilado con usuario y Cerrar sesión */}
        <div className="shrink-0 p-3 border-t border-slate-900/7 dark:border-sky-200/10">
          <div className="flex items-center justify-between gap-2 rounded-2xl border border-white/75 dark:border-sky-300/15 bg-white/65 dark:bg-[#0a1936]/75 px-2.5 py-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="h-8 w-8 flex-shrink-0 rounded-full bg-[#0022e6]/10 dark:bg-sky-400/15 flex items-center justify-center text-[#0022e6] dark:text-sky-300">
                <UserIcon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-bold text-slate-900 dark:text-white truncate">
                  {usuario.nombre_completo}
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onLogout}
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
              className="rounded-xl p-2 text-slate-600 dark:text-sky-200/80 hover:bg-slate-900/8 dark:hover:bg-white/12 hover:text-slate-900 dark:hover:text-white active:scale-95 transition-all cursor-pointer flex-shrink-0"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
