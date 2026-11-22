import { useState } from "react";
import { LoginView } from "./components/auth/LoginView";
import { ChatWorkspace } from "./components/chat/ChatWorkspace";
import { HomeView } from "./components/home/HomeView";
import { Header } from "./components/layout/Header";
import { Sidebar, type AppTab } from "./components/layout/Sidebar";
import { SettingsView } from "./components/settings/SettingsView";
import { useAuth } from "./context/AuthContext";
import { useTheme } from "./context/ThemeContext";
import { ASSETS } from "./core/config";
import { useConversations } from "./hooks/useConversations";

export default function App() {
  const { autenticado, usuario, esAdmin, cargandoSesion, logout } = useAuth();
  const { esOscuro } = useTheme();
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

  const estiloFondoAtmosferico = {
    background: esOscuro
      ? "radial-gradient(ellipse at 60% 45%, #123672 0%, #0a1e46 48%, #040c1f 100%)"
      : "radial-gradient(ellipse at 54% 46%, #eaf7ff 0%, #bce3fa 52%, #8fd0f5 100%)",
  };

  if (cargandoSesion) {
    return (
      <div
        className="flex flex-1 items-center justify-center text-slate-800 dark:text-slate-100 transition-colors"
        style={estiloFondoAtmosferico}
      >
        <div className="flex items-center gap-3 rounded-2xl border border-white/80 dark:border-sky-300/20 bg-white/75 dark:bg-[#0a1936]/80 backdrop-blur-xl px-5 py-3.5 shadow-[0_14px_36px_rgba(12,50,110,0.1)]">
          <div className="h-9 w-9 overflow-hidden rounded-full border border-white/90 dark:border-sky-300/25 bg-sky-100/80 dark:bg-[#10254c] flex items-center justify-center">
            <img
              src={ASSETS.FLUCITO_3D}
              alt="Flucito"
              className="h-full w-full object-cover object-top scale-110"
            />
          </div>
          <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
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
    <div
      className="relative flex h-full w-full overflow-hidden sm:p-2.5 lg:p-3.5 text-slate-800 dark:text-slate-100 transition-colors duration-300"
      style={estiloFondoAtmosferico}
    >
      {/* Luces atmosféricas y elementos de marca desenfocados detrás del cristal (armonía con LoginView) */}
      {esOscuro && (
        <>
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-1/5 right-1/5 h-96 w-96 rounded-full bg-sky-400/16 blur-[110px]"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute bottom-1/5 left-1/5 h-80 w-80 rounded-full bg-blue-500/16 blur-[100px]"
          />
        </>
      )}

      {/* Silueta de Flucito desenfocada abajo a la izquierda y acentos sutiles exteriores */}
      <img
        src={ASSETS.FLUCITO_3D}
        alt=""
        aria-hidden="true"
        decoding="async"
        className="pointer-events-none select-none hidden sm:block absolute -bottom-24 -left-10 z-0 w-[260px] lg:w-[300px] max-w-none object-contain blur-[5px] opacity-80 dark:opacity-55"
      />
      <img
        src={ASSETS.ENGRANAJE_CELESTE}
        alt=""
        aria-hidden="true"
        decoding="async"
        className="pointer-events-none select-none hidden md:block absolute -top-6 right-8 z-0 w-24 object-contain blur-[1.5px] opacity-75 dark:opacity-45 animate-float-b"
      />
      <img
        src={ASSETS.GOTA_AZUL}
        alt=""
        aria-hidden="true"
        decoding="async"
        className="pointer-events-none select-none hidden md:block absolute top-28 -right-3 z-0 w-12 object-contain rotate-12 blur-[1px] opacity-80 dark:opacity-50 animate-float-a"
      />
      <img
        src={ASSETS.GOTA_CELESTE}
        alt=""
        aria-hidden="true"
        decoding="async"
        className="pointer-events-none select-none hidden lg:block absolute top-10 right-52 z-0 w-9 object-contain rotate-[28deg] blur-[2px] opacity-70 dark:opacity-45"
      />

      {/* Marco principal de cristal esmerilado (Frosted Glass Workspace Shell) */}
      <div className="relative z-10 flex h-full w-full overflow-hidden sm:rounded-[26px] lg:rounded-[30px] sm:border sm:border-white/70 dark:sm:border-sky-300/20 bg-white/38 dark:bg-[#0d2044]/52 backdrop-blur-[14px] shadow-[0_24px_60px_rgba(14,70,140,0.13)] dark:shadow-[0_28px_70px_rgba(2,8,24,0.68)]">
        {/* Sidebar izquierdo colapsable en cristal esmerilado */}
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

        {/* Lienzo derecho principal */}
        <div className="relative flex flex-1 flex-col h-full min-w-0 overflow-hidden">
          <Header
            tabActiva={tabActiva}
            sidebarAbierto={sidebarAbierto}
            tituloConversacionActiva={conversacionActiva?.titulo}
            onToggleSidebar={() => setSidebarAbierto((prev) => !prev)}
            onNuevaConversacion={() => {
              iniciarNuevaConversacion();
              setTabActiva("chat");
            }}
          />

          {/* TAB 1: ChatWorkspace (UI/UX estilo ChatGPT en Glassmorphism) */}
          {tabActiva === "chat" && (
            <ChatWorkspace
              sessionId={sessionIdActivo}
              existeEnHistorial={Boolean(conversacionActiva)}
              onConversacionActualizada={() => void refrescarConversaciones(true)}
            />
          )}

          {/* TAB 2: Inicio */}
          {tabActiva === "inicio" && (
            <HomeView
              usuario={usuario}
              onSelectTab={setTabActiva}
              onNuevaConversacion={() => {
                iniciarNuevaConversacion();
                setTabActiva("chat");
              }}
            />
          )}

          {/* TAB 3: Configuración y Administración de Usuarios (Admin) */}
          {tabActiva === "configuracion" && (
            <SettingsView usuario={usuario} esAdmin={esAdmin} />
          )}
        </div>
      </div>
    </div>
  );
}
