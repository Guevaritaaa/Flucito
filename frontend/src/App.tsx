import { useState } from "react";
import { ArrowRight, CheckCircle2, Settings as SettingsIcon } from "lucide-react";
import { LoginView } from "./components/auth/LoginView";
import { ChatWorkspace } from "./components/chat/ChatWorkspace";
import { Header } from "./components/layout/Header";
import { Sidebar, type AppTab } from "./components/layout/Sidebar";
import { ASSETS } from "./core/config";
import { useAuth } from "./context/AuthContext";
import { useConversations } from "./hooks/useConversations";

export default function App() {
  const { autenticado, usuario, cargandoSesion, logout } = useAuth();
  const {
    conversaciones,
    sessionIdActivo,
    conversacionActiva,
    cargandoHistorial,
    iniciarNuevaConversacion,
    seleccionarConversacion,
    borrarConversacion,
    refrescarConversaciones,
  } = useConversations(autenticado);

  const [tabActiva, setTabActiva] = useState<AppTab>("chat");
  const [sidebarAbierto, setSidebarAbierto] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.innerWidth >= 768 : true
  );

  if (cargandoSesion) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[#f4f6fa] dark:bg-dark-canvas text-slate-700 dark:text-slate-200 transition-colors">
        <div className="flex items-center gap-3 rounded-2xl border border-cobalt-100 dark:border-slate-800 bg-white dark:bg-dark-surface px-5 py-3.5 shadow-subtle">
          <div className="h-8 w-8 overflow-hidden rounded-full ring-2 ring-cobalt-100 bg-white">
            <img
              src={ASSETS.FLUCITO_AVATAR}
              alt="Flucito"
              className="h-full w-full object-cover"
            />
          </div>
          <span className="text-sm font-medium text-cobalt-800 dark:text-slate-200">
            Verificando sesión...
          </span>
          <span className="flex items-center gap-1" aria-hidden="true">
            <span className="trabajando-punto" />
            <span className="trabajando-punto" />
            <span className="trabajando-punto" />
          </span>
        </div>
      </div>
    );
  }

  if (!autenticado || !usuario) {
    return <LoginView />;
  }

  return (
    <div className="flex h-full w-full overflow-hidden bg-[#f4f6fa] dark:bg-dark-canvas text-slate-800 dark:text-slate-100 transition-colors duration-200">
      {/* Sidebar izquierdo colapsable con historial de conversaciones y perfil */}
      <Sidebar
        abierto={sidebarAbierto}
        onToggle={() => setSidebarAbierto((prev) => !prev)}
        tabActiva={tabActiva}
        onSelectTab={setTabActiva}
        usuario={usuario}
        onLogout={logout}
        conversaciones={conversaciones}
        sessionIdActivo={sessionIdActivo}
        cargandoHistorial={cargandoHistorial}
        onNuevaConversacion={() => {
          iniciarNuevaConversacion();
          setTabActiva("chat");
        }}
        onSeleccionarConversacion={(id) => {
          seleccionarConversacion(id);
          setTabActiva("chat");
        }}
        onBorrarConversacion={borrarConversacion}
        onRefrescarHistorial={() => void refrescarConversaciones(false)}
      />

      {/* Contenedor derecho principal */}
      <div className="flex flex-1 flex-col h-full overflow-hidden">
        <Header
          tabActiva={tabActiva}
          tituloConversacionActiva={conversacionActiva?.titulo}
          onNuevaConversacion={() => {
            iniciarNuevaConversacion();
            setTabActiva("chat");
          }}
        />

        {/* TAB 1: ChatWorkspace (Principal) */}
        {tabActiva === "chat" && (
          <ChatWorkspace
            sessionId={sessionIdActivo}
            existeEnHistorial={Boolean(conversacionActiva)}
            tituloConversacion={conversacionActiva?.titulo}
            onConversacionActualizada={() => void refrescarConversaciones(true)}
          />
        )}

        {/* TAB 2: Inicio (Bienvenida amigable del prototipo) */}
        {tabActiva === "inicio" && (
          <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-12 flex flex-col items-center justify-center text-center overflow-y-auto">
            <div className="bg-white dark:bg-dark-surface border border-slate-200 dark:border-slate-800 rounded-3xl p-10 shadow-elevation max-w-xl space-y-6">
              <div className="w-20 h-20 rounded-2xl overflow-hidden mx-auto flex items-center justify-center shadow-lg ring-4 ring-cobalt-100 dark:ring-cobalt-900 bg-white">
                <img
                  src={ASSETS.FLUCITO_AVATAR}
                  alt="Flucito"
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="space-y-3">
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white">
                  ¡Bienvenido, {usuario.nombre_completo}!
                </h2>
                <p className="text-slate-600 dark:text-slate-300 text-sm leading-relaxed px-4">
                  Soy Flucito, tu asistente virtual en Interflu. Estoy conectado al catálogo de Aspel SAE y a Google Drive para ayudarte a procesar facturas y reportes de almacén.
                </p>
              </div>
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => setTabActiva("chat")}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-cobalt-600 hover:bg-cobalt-700 text-white font-semibold text-sm shadow-md hover:shadow-lg transition-all active:scale-[0.98] cursor-pointer"
                >
                  <span>Ir al Chat</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </main>
        )}

        {/* TAB 3: Configuración (Pendiente Fase 6) */}
        {tabActiva === "configuracion" && (
          <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-8 flex flex-col items-center justify-center overflow-y-auto">
            <div className="w-full max-w-xl rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-surface p-6 shadow-subtle space-y-4">
              <div className="flex items-center gap-2.5 text-sm font-bold text-cobalt-700 dark:text-cobalt-300">
                <SettingsIcon className="h-4 w-4" />
                <span>Configuración del Sistema</span>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-emerald-200/80 dark:border-emerald-800/50 bg-emerald-50/80 dark:bg-emerald-950/30 px-4 py-3 text-xs text-emerald-800 dark:text-emerald-200">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                <span>
                  Fase 5 completada. Siguiente y última fase: Panel de Configuración y Gestión de Usuarios para Admin (Fase 6).
                </span>
              </div>
            </div>
          </main>
        )}
      </div>
    </div>
  );
}
