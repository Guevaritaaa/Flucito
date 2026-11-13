import { useState } from "react";
import { LoginView } from "./components/auth/LoginView";
import { ChatWorkspace } from "./components/chat/ChatWorkspace";
import { HomeView } from "./components/home/HomeView";
import { Header } from "./components/layout/Header";
import { Sidebar, type AppTab } from "./components/layout/Sidebar";
import { SettingsView } from "./components/settings/SettingsView";
import { ASSETS } from "./core/config";
import { useAuth } from "./context/AuthContext";
import { useConversations } from "./hooks/useConversations";

export default function App() {
  const { autenticado, usuario, esAdmin, cargandoSesion, logout } = useAuth();
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
          sidebarAbierto={sidebarAbierto}
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

        {/* TAB 2: Inicio */}
        {tabActiva === "inicio" && (
          <HomeView usuario={usuario} onSelectTab={setTabActiva} />
        )}

        {/* TAB 3: Configuración y Administración de Usuarios (Admin) */}
        {tabActiva === "configuracion" && (
          <SettingsView usuario={usuario} esAdmin={esAdmin} />
        )}
      </div>
    </div>
  );
}
