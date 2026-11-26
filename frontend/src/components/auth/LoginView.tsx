import { useState, type FormEvent } from "react";
import {
  AlertCircle,
  Clock,
  Eye,
  EyeOff,
  Info,
  Moon,
  Sun,
} from "lucide-react";
import { ASSETS } from "../../core/config";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../context/ThemeContext";
import { ApiError } from "../../services/http";

export function LoginView() {
  const { login } = useAuth();
  const { esOscuro, toggleTheme } = useTheme();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mostrarPassword, setMostrarPassword] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [esBloqueoTemporal, setEsBloqueoTemporal] = useState(false);
  const [avisoAyuda, setAvisoAyuda] = useState<string | null>(null);

  async function manejarSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setAvisoAyuda(null);
    const usuarioLimpio = username.trim().toLowerCase();
    if (!usuarioLimpio || !password) {
      setErrorMsg("Ingresa tu usuario y contraseña para continuar.");
      setEsBloqueoTemporal(false);
      return;
    }

    setEnviando(true);
    setErrorMsg(null);
    setEsBloqueoTemporal(false);

    try {
      await login({ username: usuarioLimpio, password });
    } catch (err) {
      if (err instanceof ApiError) {
        setEsBloqueoTemporal(err.isRateLimited);
        setErrorMsg(err.message);
      } else {
        setEsBloqueoTemporal(false);
        setErrorMsg(
          "No fue posible conectar con el servidor de Flucito. Verifica que el backend esté activo."
        );
      }
    } finally {
      setEnviando(false);
    }
  }

  const selectorTema = (
    <>
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={esOscuro ? "Activar modo claro" : "Activar modo oscuro"}
        className="flex h-11 w-11 md:h-10 md:w-10 items-center justify-center rounded-xl border border-white/65 dark:border-sky-300/25 bg-white/45 dark:bg-[#0e2248]/65 backdrop-blur-md text-slate-700 dark:text-slate-100 shadow-subtle hover:bg-white/75 dark:hover:bg-[#152f61]/80 active:scale-[0.96] transition-all duration-150 cursor-pointer"
      >
        {esOscuro ? (
          <Sun className="h-4 w-4 text-amber-300 transition-transform duration-200 group-hover:rotate-12" />
        ) : (
          <Moon className="h-4 w-4 text-[#0018cc] transition-transform duration-200 group-hover:-rotate-12" />
        )}
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute hidden md:block right-0 top-full mt-2 z-50 whitespace-nowrap rounded-lg bg-slate-900/95 border border-white/15 px-2.5 py-1 text-[11px] font-medium text-white shadow-md opacity-0 scale-95 origin-top-right group-hover:opacity-100 group-hover:scale-100 group-focus-within:opacity-100 group-focus-within:scale-100 transition-all duration-150 ease-out"
      >
        {esOscuro ? "Activar modo claro" : "Activar modo oscuro"}
      </span>
    </>
  );

  return (
    <main
      className="relative flex h-full w-full flex-col items-center overflow-y-auto overflow-x-hidden custom-scroll px-3 py-3 sm:px-6 md:py-8 lg:px-8 transition-colors duration-300 select-none"
      style={{
        background: esOscuro
          ? "radial-gradient(ellipse at 60% 45%, #123672 0%, #0a1e46 48%, #040c1f 100%)"
          : "radial-gradient(ellipse at 54% 46%, #eaf7ff 0%, #bce3fa 52%, #8fd0f5 100%)",
      }}
    >
      {/* Luces atmosféricas en Modo Oscuro para dar refracción real al cristal */}
      {esOscuro && (
        <>
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-1/4 right-1/4 h-80 w-80 rounded-full bg-sky-400/18 blur-[100px]"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute bottom-1/4 left-1/4 h-72 w-72 rounded-full bg-blue-500/18 blur-[95px]"
          />
        </>
      )}

      <div className="group absolute top-6 right-6 z-30 hidden md:block">
        {selectorTema}
      </div>

      {/* Escena principal centrada */}
      <div className="relative w-full max-w-[420px] md:max-w-[920px] flex shrink-0 items-center justify-center md:my-auto">
        {/* Capa 0: Flucito desenfocado en la esquina inferior izquierda (usando flucito-mascota-3d.webp nativo sin residuos de fondo) */}
        <img
          src={ASSETS.FLUCITO_3D}
          alt=""
          aria-hidden="true"
          decoding="async"
          className="pointer-events-none select-none hidden sm:block absolute -bottom-28 -left-16 md:-bottom-32 md:-left-20 z-0 w-[290px] md:w-[335px] max-w-none object-contain blur-[5px] opacity-85 dark:opacity-65"
        />

        {/* Capa 1: Marco exterior de cristal esmerilado (Frosted Glass Container) */}
        <div className="relative z-10 w-full md:min-h-[495px] rounded-[30px] border border-white/65 dark:border-sky-300/20 bg-white/30 dark:bg-[#0d2044]/45 backdrop-blur-[12px] shadow-[0_24px_60px_rgba(14,70,140,0.12)] dark:shadow-[0_28px_70px_rgba(2,8,24,0.65)] p-3 md:px-11 md:py-10 flex flex-col md:flex-row items-center gap-3 md:gap-4">
          {/* Columna Izquierda: Tarjeta interna translúcida del formulario */}
          <div className="relative z-20 w-full md:max-w-[355px] md:w-[46%] flex-shrink-0 rounded-[22px] border border-white/85 dark:border-sky-200/20 bg-white/72 dark:bg-[#0a1936]/78 backdrop-blur-xl px-4 py-5 md:px-8 md:py-8 shadow-[0_12px_32px_rgba(12,50,110,0.08)] dark:shadow-[0_16px_40px_rgba(2,8,26,0.55)]">
            {/* Cabecera integrada: Logo Interflu con proporción exacta respecto a "Iniciar sesión" */}
            <div className="mb-4 md:mb-5">
              <div className="mb-3 flex items-center justify-between gap-2 md:mb-5">
                <img
                  src={esOscuro ? ASSETS.INTERFLU_LOGO_DARK : ASSETS.INTERFLU_LOGO}
                  alt="Interflu - Internacional de Fluidos, S.A. de C.V."
                  className="w-[140px] sm:w-[148px] h-auto object-contain select-none"
                />
                <div className="md:hidden">{selectorTema}</div>
              </div>
              <h1 className="text-[24px] sm:text-[26px] leading-tight font-extrabold tracking-tight text-slate-900 dark:text-white">
                Iniciar sesión
              </h1>
            </div>

            {/* Mensajes de error de autenticación o rate-limit */}
            {errorMsg && (
              <div
                role="alert"
                className={`mb-4 flex items-start gap-2 rounded-xl border p-3 text-xs leading-relaxed select-text ${
                  esBloqueoTemporal
                    ? "border-amber-300/90 bg-amber-50/90 text-amber-900 dark:border-amber-600/50 dark:bg-amber-950/60 dark:text-amber-200"
                    : "border-red-300/90 bg-red-50/90 text-red-800 dark:border-red-700/50 dark:bg-red-950/60 dark:text-red-200"
                }`}
              >
                {esBloqueoTemporal ? (
                  <Clock className="h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
                ) : (
                  <AlertCircle className="h-4 w-4 flex-shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
                )}
                <span className="font-medium">{errorMsg}</span>
              </div>
            )}

            {/* Aviso informativo al pulsar Olvidaste tu contraseña / Solicitar acceso */}
            {avisoAyuda && !errorMsg && (
              <div
                role="status"
                className="mb-4 flex items-start gap-2 rounded-xl border border-sky-200 dark:border-sky-400/25 bg-white/90 dark:bg-[#10254c]/90 p-3 text-xs leading-relaxed text-slate-700 dark:text-sky-100 select-text"
              >
                <Info className="h-4 w-4 flex-shrink-0 text-[#0022e6] dark:text-sky-400 mt-0.5" />
                <span>{avisoAyuda}</span>
              </div>
            )}

            <form onSubmit={(e) => void manejarSubmit(e)} className="space-y-4" noValidate>
              {/* Campo 1: Usuario */}
              <div className="space-y-1.5">
                <label
                  htmlFor="login-username"
                  className="block text-xs font-semibold text-slate-800 dark:text-slate-200"
                >
                  Usuario
                </label>
                <input
                  id="login-username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  disabled={enviando}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Ingresa tu usuario"
                  className="w-full rounded-xl border border-white dark:border-sky-300/20 bg-white dark:bg-[#071229]/90 px-3.5 py-2.5 text-base md:text-sm pointer-coarse:text-base text-slate-800 dark:text-white placeholder-slate-400 dark:placeholder-slate-400/80 shadow-[0_2px_8px_rgba(15,23,42,0.04)] transition-all focus:border-[#0022e6] dark:focus:border-sky-400 focus:ring-2 focus:ring-[#0022e6]/15 dark:focus:ring-sky-400/20 focus:outline-none disabled:opacity-60 select-text"
                />
              </div>

              {/* Campo 2: Contraseña */}
              <div className="space-y-1.5">
                <label
                  htmlFor="login-password"
                  className="block text-xs font-semibold text-slate-800 dark:text-slate-200"
                >
                  Contraseña
                </label>
                <div className="relative">
                  <input
                    id="login-password"
                    name="password"
                    type={mostrarPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    disabled={enviando}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="•••••••••"
                    className="w-full rounded-xl border border-white dark:border-sky-300/20 bg-white dark:bg-[#071229]/90 py-2.5 pl-3.5 pr-11 text-base md:text-sm pointer-coarse:text-base text-slate-800 dark:text-white placeholder-slate-400 dark:placeholder-slate-400/80 shadow-[0_2px_8px_rgba(15,23,42,0.04)] transition-all focus:border-[#0022e6] dark:focus:border-sky-400 focus:ring-2 focus:ring-[#0022e6]/15 dark:focus:ring-sky-400/20 focus:outline-none disabled:opacity-60 select-text"
                  />
                  <button
                    type="button"
                    onClick={() => setMostrarPassword((prev) => !prev)}
                    tabIndex={-1}
                    aria-label={
                      mostrarPassword ? "Ocultar contraseña" : "Mostrar contraseña"
                    }
                    className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-slate-400 hover:text-slate-600 dark:text-slate-400 dark:hover:text-sky-300 cursor-pointer"
                  >
                    {mostrarPassword ? (
                      <Eye className="h-4 w-4" />
                    ) : (
                      <EyeOff className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              {/* Botón Principal: Entrar */}
              <div className="pt-1.5">
                <button
                  type="submit"
                  disabled={enviando}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#0022e6] hover:bg-[#0018cc] dark:bg-[#1d4ed8] dark:hover:bg-[#2563eb] active:scale-[0.99] min-h-11 px-5 py-2.5 text-sm font-semibold text-white shadow-[0_6px_20px_rgba(0,34,230,0.34)] dark:shadow-[0_6px_22px_rgba(29,78,216,0.45)] transition-all disabled:opacity-60 disabled:pointer-events-none cursor-pointer"
                >
                  {enviando ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                      <span>Verificando...</span>
                    </>
                  ) : (
                    <span>Entrar</span>
                  )}
                </button>
              </div>
            </form>

            {/* Enlaces inferiores adaptados al flujo empresarial de Interflu */}
            <div className="mt-4 text-center space-y-2.5 md:mt-5">
              <div>
                <button
                  type="button"
                  onClick={() => {
                    setErrorMsg(null);
                    setAvisoAyuda(
                      "Para restablecer tu contraseña, contacta a la administración."
                    );
                  }}
                  className="text-xs font-medium text-[#1d4ed8] dark:text-sky-300 hover:text-[#0022e6] dark:hover:text-white hover:underline transition-colors cursor-pointer"
                >
                  ¿Olvidaste tu contraseña?
                </button>
              </div>

              <p className="text-xs text-slate-700 dark:text-slate-300 pt-0.5">
                ¿No tienes cuenta?{" "}
                <button
                  type="button"
                  onClick={() => {
                    setErrorMsg(null);
                    setAvisoAyuda(
                      "Las cuentas son asignadas por administración. Próximamente podrás enviar tu solicitud de acceso desde aquí."
                    );
                  }}
                  className="font-semibold text-[#1d4ed8] dark:text-sky-300 hover:text-[#0022e6] dark:hover:text-white hover:underline transition-colors cursor-pointer"
                >
                  Solicitar acceso
                </button>
              </p>
            </div>
          </div>

          {/* Columna Derecha: Composición multicapa con recursos nativos PNG de public/Recursos */}
          <div className="relative z-20 md:flex-1 md:min-h-[450px] w-full min-w-0 flex items-center justify-center">
            <div className="relative w-full max-w-[270px] aspect-square md:max-w-none md:w-[440px] lg:w-[470px] md:h-[470px] flex items-center justify-center md:-my-10 md:-mr-6">
              {/* --- ELEMENTOS DECORATIVOS FLOTANTES (Detrás y alrededor de Flucito) --- */}

              {/* Arriba-Izquierda: Espiral cian pequeña + gota inclinada */}
              <img
                src={ASSETS.ESPIRAL_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[1%] left-[25%] w-11 sm:w-13 h-auto object-contain animate-float-b drop-shadow-[0_6px_12px_rgba(14,116,144,0.18)]"
              />
              <img
                src={ASSETS.GOTA_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute -top-[1%] left-[44%] w-6 sm:w-7 h-auto object-contain rotate-[65deg] animate-float-a"
              />

              {/* Arriba-Derecha: Engranaje metálico grande (engranaje metalico) + Engranaje celeste (engranaje celeste) + Tuerca pequeña */}
              <img
                src={ASSETS.ENGRANAJE_METALICO}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute -top-[3%] right-[19%] w-15 sm:w-18 md:w-20 h-auto object-contain animate-float-a drop-shadow-[0_8px_16px_rgba(15,23,42,0.18)]"
              />
              <img
                src={ASSETS.ENGRANAJE_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[10%] right-[13%] w-8 sm:w-10 h-auto object-contain animate-float-b drop-shadow-[0_4px_10px_rgba(14,116,144,0.2)]"
              />
              <img
                src={ASSETS.ENGRANAJE_METALICO}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[14%] right-[7%] w-5 sm:w-6 h-auto object-contain animate-float-a opacity-90"
              />

              {/* Izquierda-Superior (junto al casco): gota celeste mediana y pequeña */}
              <img
                src={ASSETS.GOTA_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[11%] left-[12%] w-10 sm:w-12 h-auto object-contain rotate-[32deg] animate-float-a drop-shadow-[0_6px_12px_rgba(2,132,199,0.22)]"
              />
              <img
                src={ASSETS.GOTA_AZUL}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[21%] left-[14%] w-5 sm:w-6 h-auto object-contain rotate-[-12deg] animate-float-b"
              />

              {/* Izquierda-Media: Gotas azules reales (gota azul) */}
              <img
                src={ASSETS.GOTA_AZUL}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[28%] left-[5%] w-11 sm:w-13 h-auto object-contain rotate-[22deg] animate-float-b drop-shadow-[0_8px_16px_rgba(0,34,230,0.24)]"
              />
              <img
                src={ASSETS.GOTA_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[39%] left-[7%] w-7 sm:w-9 h-auto object-contain rotate-[-6deg] animate-float-a"
              />

              {/* Izquierda-Media-Baja: Espiral cian grande */}
              <img
                src={ASSETS.ESPIRAL_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[49%] -left-[2%] w-15 sm:w-18 md:w-20 h-auto object-contain -rotate-12 animate-float-a drop-shadow-[0_8px_16px_rgba(6,182,212,0.22)]"
              />

              {/* Abajo-Izquierda (junto a la mano derecha de Flucito): Engranaje metálico grande (engranaje metalico) + Engranaje azul (engranaje azul) */}
              <img
                src={ASSETS.ENGRANAJE_METALICO}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute bottom-[12%] left-[1%] z-10 w-22 sm:w-26 md:w-28 h-auto object-contain rotate-12 animate-float-b drop-shadow-[0_12px_22px_rgba(15,23,42,0.22)]"
              />
              <img
                src={ASSETS.ENGRANAJE_AZUL}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute bottom-[18%] left-[25%] z-10 w-8 sm:w-9 h-auto object-contain animate-float-a drop-shadow-[0_6px_12px_rgba(0,34,230,0.25)]"
              />

              {/* Derecha-Media y Baja: Splash de agua (salpicadura de agua) + Gotas + Engranajes inferiores */}
              <img
                src={ASSETS.GOTA_AZUL}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute top-[43%] right-[6%] w-8 sm:w-10 h-auto object-contain -rotate-12 animate-float-a drop-shadow-[0_6px_14px_rgba(0,34,230,0.22)]"
              />
              <img
                src={ASSETS.SALPICADURA_AGUA}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute bottom-[24%] right-[2%] w-16 sm:w-20 h-auto object-contain rotate-12 animate-float-b drop-shadow-[0_8px_18px_rgba(2,132,199,0.25)]"
              />
              <img
                src={ASSETS.GOTA_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute bottom-[15%] right-[14%] w-7 sm:w-8 h-auto object-contain -rotate-45 animate-float-a"
              />
              <img
                src={ASSETS.ENGRANAJE_AZUL}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute bottom-[1%] right-[6%] w-9 sm:w-11 h-auto object-contain animate-float-b drop-shadow-[0_6px_14px_rgba(0,34,230,0.28)]"
              />
              <img
                src={ASSETS.ENGRANAJE_CELESTE}
                alt=""
                aria-hidden="true"
                className="pointer-events-none absolute bottom-[7%] right-[2%] w-6 sm:w-7 h-auto object-contain animate-float-a"
              />

              {/* --- PERSONAJE CENTRAL: Flucito 3D Nativo (flucito-mascota-3d.webp) --- */}
              <img
                src={ASSETS.FLUCITO_3D}
                alt="Flucito - Mascota Oficial Team Interflu"
                width={681}
                height={900}
                fetchPriority="high"
                className="relative z-20 w-[62%] md:w-[345px] md:max-w-[94%] lg:w-[365px] h-auto object-contain select-none pointer-events-none animate-flucito-float drop-shadow-[0_18px_32px_rgba(8,45,105,0.22)] dark:drop-shadow-[0_20px_38px_rgba(0,0,0,0.45)]"
              />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
