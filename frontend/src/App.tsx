import { useEffect, useState } from "react";
import { LoginView } from "./components/auth/LoginView";
import { ChatWorkspace } from "./components/chat/ChatWorkspace";
import { HomeView } from "./components/home/HomeView";
import { Header } from "./components/layout/Header";
import { Sidebar, type AppTab } from "./components/layout/Sidebar";
import { SettingsView } from "./components/settings/SettingsView";
import { PanelSae } from "./components/sae/PanelSae";
import { useAuth } from "./context/AuthContext";
import { useTheme } from "./context/ThemeContext";
import { ASSETS } from "./core/config";
import { useVisibleViewport } from "./hooks/useVisibleViewport";
import { useConversations } from "./hooks/useConversations";
import { ACCESO_SAE_REQUERIDO, CHAT_SAE_BLOQUEADO, esIdChatSae } from "./schemas/chat";

export default function App() {
  useVisibleViewport();
  const { autenticado, usuario, esAdmin, cargandoSesion, logout, recargarPerfil } = useAuth();
  const accesoSae = usuario?.acceso_sae === true;
  const { esOscuro } = useTheme();
  const {
    conversaciones,
    sessionIdActivo,
    conversacionActiva,
    cargandoHistorial,
    iniciarNuevaConversacion,
    iniciarConversacionSae,
    seleccionarConversacion,
    borrarConversacion,
    refrescarConversaciones,
  } = useConversations(autenticado, accesoSae);

  const [tabActiva, setTabActiva] = useState<AppTab>("inicio");
  const [borradorSae, setBorradorSae] = useState<{ id: string; texto: string } | null>(null);
  const [creandoSae, setCreandoSae] = useState(false);
  const [errorSae, setErrorSae] = useState<string | null>(null);
  const [sidebarAbierto, setSidebarAbierto] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.innerWidth >= 768 : true
  );

  useEffect(() => {
    if (!autenticado) {
      setTabActiva("inicio");
      setBorradorSae(null);
      setErrorSae(null);
      return;
    }
    const chat = new URLSearchParams(window.location.search).get("chat");
    if (chat && esIdChatSae(chat)) {
      seleccionarConversacion(chat);
      setTabActiva("chat");
    }
  }, [autenticado, seleccionarConversacion]);

  useEffect(() => {
    if (!autenticado) return;
    const actualizar = () => {
      if (document.visibilityState === "visible") void recargarPerfil(true);
    };
    const intervalo = window.setInterval(actualizar, 10000);
    window.addEventListener("focus", actualizar);
    return () => {
      window.clearInterval(intervalo);
      window.removeEventListener("focus", actualizar);
    };
  }, [autenticado, recargarPerfil]);

  const esChatSae = conversacionActiva?.tipo === "sae" || esIdChatSae(sessionIdActivo);
  const bloqueadoSae = esChatSae && (!accesoSae || conversacionActiva?.bloqueada);
  useEffect(() => {
    if (!accesoSae) setBorradorSae(null);
  }, [accesoSae]);

  function actualizarUrlChat(id?: string) {
    const url = new URL(window.location.href);
    if (id && esIdChatSae(id)) url.searchParams.set("chat", id);
    else url.searchParams.delete("chat");
    window.history.replaceState(window.history.state, "", url);
  }

  function nuevoChatCotidiano() {
    setErrorSae(null);
    iniciarNuevaConversacion();
    actualizarUrlChat();
    setTabActiva("chat");
  }

  async function abrirChatSae(texto = "") {
    if (!accesoSae || creandoSae) return;
    setCreandoSae(true);
    setErrorSae(null);
    try {
      const id = await iniciarConversacionSae();
      setBorradorSae({ id, texto });
      seleccionarConversacion(id);
      actualizarUrlChat(id);
      setTabActiva("chat");
      if (window.innerWidth < 768) setSidebarAbierto(false);
    } catch (err) {
      setErrorSae(err instanceof Error ? err.message : "No se pudo abrir el chat de Aspel SAE.");
      void recargarPerfil(true);
    } finally {
      setCreandoSae(false);
    }
  }

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
          onSelectTab={(tab) => {
            if (tab === "sae") {
              actualizarUrlChat();
              setErrorSae(null);
            }
            setTabActiva(tab);
          }}
          usuario={usuario}
          onLogout={logout}
          conversaciones={conversaciones}
          sessionIdActivo={sessionIdActivo}
          cargandoHistorial={cargandoHistorial}
          onNuevaConversacion={nuevoChatCotidiano}
          onAbrirChatSae={() => void abrirChatSae()}
          creandoSae={creandoSae}
          onSeleccionarConversacion={(id) => {
            setErrorSae(null);
            seleccionarConversacion(id);
            actualizarUrlChat(id);
            setTabActiva("chat");
          }}
          onBorrarConversacion={borrarConversacion}
          onRefrescarHistorial={() => void refrescarConversaciones(false)}
        />

        {/* Lienzo derecho principal */}
        <div className="relative flex flex-1 flex-col h-full min-w-0 overflow-hidden @container-size">
          <Header
            tabActiva={tabActiva}
            sidebarAbierto={sidebarAbierto}
            tituloConversacionActiva={bloqueadoSae ? "Chat de Aspel SAE" : conversacionActiva?.titulo}
            onToggleSidebar={() => setSidebarAbierto((prev) => !prev)}
            onNuevaConversacion={nuevoChatCotidiano}
          />
          {errorSae && <p role="alert" className="mx-auto mb-2 px-4 text-sm text-red-700 dark:text-red-200">{errorSae}</p>}

          {/* TAB 1: ChatWorkspace (UI/UX estilo ChatGPT en Glassmorphism) */}
          {tabActiva === "chat" && (bloqueadoSae ? (
            <p role="status" className="m-auto max-w-md px-5 text-center text-sm text-slate-700 dark:text-slate-200">
              {CHAT_SAE_BLOQUEADO}
            </p>
          ) : (
            <ChatWorkspace
              key={sessionIdActivo}
              sessionId={sessionIdActivo}
              existeEnHistorial={Boolean(conversacionActiva) || esChatSae}
              esChatSae={esChatSae}
              accesoSae={accesoSae}
              creandoSae={creandoSae}
              borradorInicial={borradorSae?.id === sessionIdActivo ? borradorSae.texto : ""}
              onBorradorConsumido={() => setBorradorSae(null)}
              onAbrirChatSae={(texto) => void abrirChatSae(texto)}
              onConversacionActualizada={() => void refrescarConversaciones(true)}
            />
          ))}

          {/* TAB 2: Inicio */}
          {tabActiva === "inicio" && (
            <HomeView
              usuario={usuario}
              onSelectTab={setTabActiva}
              onNuevaConversacion={nuevoChatCotidiano}
            />
          )}

          {/* TAB 3: Configuración y Administración de Usuarios (Admin) */}
          {tabActiva === "configuracion" && (
            <SettingsView usuario={usuario} esAdmin={esAdmin} />
          )}

          {tabActiva === "sae" && (accesoSae ? (
            <PanelSae creandoChat={creandoSae} onPreguntar={(mensaje) => void abrirChatSae(mensaje)} onRevalidarAcceso={recargarPerfil} />
          ) : (
            <p role="status" className="m-auto max-w-md px-5 text-center text-sm">{ACCESO_SAE_REQUERIDO}</p>
          ))}
        </div>
      </div>
    </div>
  );
}
