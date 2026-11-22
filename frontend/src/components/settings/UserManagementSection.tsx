import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  AlertCircle,
  Check,
  KeyRound,
  Plus,
  RefreshCw,
  Shield,
  UserCheck,
  UserPlus,
  UserX,
  X,
} from "lucide-react";
import type { RolUsuario, UsuarioOut } from "../../schemas/auth";
import {
  actualizarUsuario,
  crearUsuario,
  listarUsuarios,
} from "../../services/authService";
import { ApiError } from "../../services/http";

interface UserManagementSectionProps {
  usuarioActualId: number;
}

function formatearFechaCorta(iso: string | null): string {
  if (!iso) return "Sin registro";
  try {
    return new Date(iso).toLocaleString("es-MX", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

export function UserManagementSection({
  usuarioActualId,
}: UserManagementSectionProps) {
  const [usuarios, setUsuarios] = useState<UsuarioOut[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);

  // Estado para formulario inline de nuevo usuario
  const [mostrarFormNuevo, setMostrarFormNuevo] = useState(false);
  const [nuevoUsername, setNuevoUsername] = useState("");
  const [nuevoNombre, setNuevoNombre] = useState("");
  const [nuevoPassword, setNuevoPassword] = useState("");
  const [nuevoRol, setNuevoRol] = useState<RolUsuario>("operador");
  const [creando, setCreando] = useState(false);

  // Estado para cambio de contraseña inline por fila
  const [editandoPassId, setEditandoPassId] = useState<number | null>(null);
  const [nuevaPassFila, setNuevaPassFila] = useState("");
  const [procesandoFilaId, setProcesandoFilaId] = useState<number | null>(null);

  const cargarListaUsuarios = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const data = await listarUsuarios();
      setUsuarios(data);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo cargar la lista de usuarios."
      );
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargarListaUsuarios();
  }, [cargarListaUsuarios]);

  function mostrarAvisoTemporal(texto: string) {
    setMensajeExito(texto);
    window.setTimeout(() => {
      setMensajeExito((actual) => (actual === texto ? null : actual));
    }, 3500);
  }

  async function manejarCrearUsuario(e: FormEvent) {
    e.preventDefault();
    if (!nuevoUsername.trim() || !nuevoNombre.trim() || nuevoPassword.length < 6) {
      setError(
        "Completa usuario, nombre y una contraseña de al menos 6 caracteres."
      );
      return;
    }

    setCreando(true);
    setError(null);
    try {
      const creado = await crearUsuario({
        username: nuevoUsername.trim().toLowerCase(),
        nombre_completo: nuevoNombre.trim(),
        password: nuevoPassword,
        rol: nuevoRol,
      });
      setUsuarios((prev) => [...prev, creado]);
      setNuevoUsername("");
      setNuevoNombre("");
      setNuevoPassword("");
      setNuevoRol("operador");
      setMostrarFormNuevo(false);
      mostrarAvisoTemporal(`Usuario @${creado.username} creado correctamente.`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No fue posible crear el usuario."
      );
    } finally {
      setCreando(false);
    }
  }

  async function alternarEstadoActivo(u: UsuarioOut) {
    if (u.id === usuarioActualId) return;
    setProcesandoFilaId(u.id);
    setError(null);
    try {
      const actualizado = await actualizarUsuario(u.id, {
        activo: !u.activo,
      });
      setUsuarios((prev) =>
        prev.map((item) => (item.id === u.id ? actualizado : item))
      );
      mostrarAvisoTemporal(
        `Cuenta @${u.username} ${actualizado.activo ? "activada" : "desactivada"}.`
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo actualizar el estado del usuario."
      );
    } finally {
      setProcesandoFilaId(null);
    }
  }

  async function alternarRol(u: UsuarioOut) {
    const siguienteRol: RolUsuario = u.rol === "admin" ? "operador" : "admin";
    setProcesandoFilaId(u.id);
    setError(null);
    try {
      const actualizado = await actualizarUsuario(u.id, {
        rol: siguienteRol,
      });
      setUsuarios((prev) =>
        prev.map((item) => (item.id === u.id ? actualizado : item))
      );
      mostrarAvisoTemporal(
        `Rol de @${u.username} actualizado a ${siguienteRol}.`
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo cambiar el rol del usuario."
      );
    } finally {
      setProcesandoFilaId(null);
    }
  }

  async function guardarNuevaPassword(usuarioId: number, username: string) {
    if (nuevaPassFila.length < 6) {
      setError("La nueva contraseña debe tener al menos 6 caracteres.");
      return;
    }
    setProcesandoFilaId(usuarioId);
    setError(null);
    try {
      await actualizarUsuario(usuarioId, { password: nuevaPassFila });
      setEditandoPassId(null);
      setNuevaPassFila("");
      mostrarAvisoTemporal(`Contraseña de @${username} actualizada.`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo actualizar la contraseña."
      );
    } finally {
      setProcesandoFilaId(null);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-extrabold tracking-tight text-slate-900 dark:text-white">
              Administración de Cuentas de Usuario
            </h2>
            <span className="inline-flex items-center gap-1 rounded-md border border-[#0022e6]/20 dark:border-sky-400/25 bg-[#0022e6]/10 dark:bg-sky-400/15 px-2 py-0.5 text-[11px] font-semibold text-[#0018cc] dark:text-sky-200">
              <Shield className="h-3 w-3" />
              <span>Solo Admin</span>
            </span>
          </div>
          <p className="text-xs font-medium text-slate-600 dark:text-sky-100/75 mt-0.5">
            Gestiona quién puede iniciar sesión en Flucito y su nivel de acceso.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void cargarListaUsuarios()}
            disabled={cargando}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/85 dark:border-sky-300/20 bg-white/75 dark:bg-[#0e2248]/75 hover:bg-white dark:hover:bg-[#152f61]/90 backdrop-blur-md px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-100 active:scale-[0.98] transition-all cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${cargando ? "animate-spin" : ""}`} />
            <span>Actualizar</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setMostrarFormNuevo((prev) => !prev);
              setError(null);
            }}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[#0022e6] hover:bg-[#0018cc] dark:bg-[#1d4ed8] dark:hover:bg-[#2563eb] active:scale-[0.98] px-3.5 py-2 text-xs font-semibold text-white shadow-[0_6px_18px_rgba(0,34,230,0.28)] transition-all cursor-pointer"
          >
            {mostrarFormNuevo ? (
              <>
                <X className="h-3.5 w-3.5" />
                <span>Cancelar</span>
              </>
            ) : (
              <>
                <UserPlus className="h-3.5 w-3.5" />
                <span>Nuevo usuario</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Alertas de error o éxito */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-2.5 rounded-xl border border-red-300/90 dark:border-red-800/60 bg-red-50/90 dark:bg-red-950/60 px-4 py-3 text-xs font-medium text-red-800 dark:text-red-200"
        >
          <AlertCircle className="h-4 w-4 flex-shrink-0 text-red-600 dark:text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {mensajeExito && (
        <div
          role="status"
          className="flex items-center gap-2.5 rounded-xl border border-emerald-300/80 dark:border-emerald-800/60 bg-emerald-50/90 dark:bg-emerald-950/60 px-4 py-3 text-xs font-medium text-emerald-800 dark:text-emerald-200"
        >
          <Check className="h-4 w-4 flex-shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>{mensajeExito}</span>
        </div>
      )}

      {/* Formulario inline para crear nuevo usuario */}
      {mostrarFormNuevo && (
        <form
          onSubmit={(e) => void manejarCrearUsuario(e)}
          className="rounded-2xl border border-white/85 dark:border-sky-300/20 bg-white/78 dark:bg-[#0a1936]/82 backdrop-blur-xl p-5 shadow-[0_12px_32px_rgba(12,50,110,0.08)] space-y-4"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Registrar nueva cuenta
            </h3>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1">
              <label className="block text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                Usuario (login)
              </label>
              <input
                type="text"
                required
                minLength={2}
                placeholder="ej. almacen2"
                value={nuevoUsername}
                onChange={(e) => setNuevoUsername(e.target.value)}
                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-canvas px-3 py-2 text-xs text-slate-800 dark:text-slate-100 focus:border-cobalt-600 focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                Nombre completo
              </label>
              <input
                type="text"
                required
                minLength={2}
                placeholder="ej. Juan Pérez"
                value={nuevoNombre}
                onChange={(e) => setNuevoNombre(e.target.value)}
                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-canvas px-3 py-2 text-xs text-slate-800 dark:text-slate-100 focus:border-cobalt-600 focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                Contraseña inicial
              </label>
              <input
                type="password"
                required
                minLength={6}
                placeholder="Mínimo 6 caracteres"
                value={nuevoPassword}
                onChange={(e) => setNuevoPassword(e.target.value)}
                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-canvas px-3 py-2 text-xs text-slate-800 dark:text-slate-100 focus:border-cobalt-600 focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                Rol de acceso
              </label>
              <select
                value={nuevoRol}
                onChange={(e) => setNuevoRol(e.target.value as RolUsuario)}
                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-canvas px-3 py-2 text-xs font-medium text-slate-800 dark:text-slate-100 focus:border-cobalt-600 focus:outline-none"
              >
                <option value="operador">Operador</option>
                <option value="admin">Administrador</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setMostrarFormNuevo(false)}
              className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated px-3.5 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 cursor-pointer"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={creando}
              className="inline-flex items-center gap-1.5 rounded-xl bg-cobalt-600 hover:bg-cobalt-700 active:scale-[0.98] px-4 py-2 text-xs font-semibold text-white shadow-sm disabled:opacity-60 cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>{creando ? "Guardando..." : "Crear cuenta"}</span>
            </button>
          </div>
        </form>
      )}

      {/* Tabla de usuarios registrados */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-surface shadow-subtle">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-dark-canvas text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                <th className="py-3 px-4">Usuario</th>
                <th className="py-3 px-4">Rol</th>
                <th className="py-3 px-4">Estado</th>
                <th className="py-3 px-4">Último acceso</th>
                <th className="py-3 px-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
              {cargando && usuarios.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    Cargando usuarios registrados...
                  </td>
                </tr>
              ) : (
                usuarios.map((u) => {
                  const esMiCuenta = u.id === usuarioActualId;
                  const editandoPass = editandoPassId === u.id;
                  const procesando = procesandoFilaId === u.id;

                  return (
                    <tr
                      key={u.id}
                      className="hover:bg-slate-50/70 dark:hover:bg-dark-elevated/40 transition-colors"
                    >
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                          <span>{u.nombre_completo}</span>
                          {esMiCuenta && (
                            <span className="rounded bg-cobalt-50 dark:bg-cobalt-950 border border-cobalt-200 dark:border-cobalt-800 px-1.5 py-0.2 text-[10px] font-semibold text-cobalt-700 dark:text-cobalt-300">
                              Tú
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-500 dark:text-slate-400">
                          @{u.username}
                        </div>
                      </td>

                      <td className="py-3.5 px-4">
                        <button
                          type="button"
                          disabled={procesando || esMiCuenta}
                          onClick={() => void alternarRol(u)}
                          title={
                            esMiCuenta
                              ? "No puedes cambiar tu propio rol"
                              : "Clic para alternar entre Admin y Operador"
                          }
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold border transition-colors ${
                            u.rol === "admin"
                              ? "border-cobalt-200 dark:border-cobalt-800 bg-cobalt-50 dark:bg-cobalt-950/70 text-cobalt-700 dark:text-cobalt-300"
                              : "border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-dark-canvas text-slate-700 dark:text-slate-300"
                          } ${!esMiCuenta ? "hover:border-cobalt-400 cursor-pointer" : "opacity-90"}`}
                        >
                          <Shield className="h-3 w-3" />
                          <span className="capitalize">{u.rol}</span>
                        </button>
                      </td>

                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold border ${
                            u.activo
                              ? "border-emerald-200 dark:border-emerald-800/60 bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300"
                              : "border-red-200 dark:border-red-800/60 bg-red-50 dark:bg-red-950/50 text-red-700 dark:text-red-300"
                          }`}
                        >
                          {u.activo ? (
                            <>
                              <UserCheck className="h-3 w-3" />
                              <span>Activo</span>
                            </>
                          ) : (
                            <>
                              <UserX className="h-3 w-3" />
                              <span>Inactivo</span>
                            </>
                          )}
                        </span>
                      </td>

                      <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400">
                        {formatearFechaCorta(u.ultimo_login)}
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        {editandoPass ? (
                          <div className="inline-flex items-center justify-end gap-1.5">
                            <input
                              type="password"
                              placeholder="Nueva contraseña (mín. 6)"
                              value={nuevaPassFila}
                              onChange={(e) => setNuevaPassFila(e.target.value)}
                              className="w-40 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-dark-canvas px-2.5 py-1 text-xs text-slate-800 dark:text-slate-100 focus:border-cobalt-600 focus:outline-none"
                            />
                            <button
                              type="button"
                              disabled={procesando}
                              onClick={() =>
                                void guardarNuevaPassword(u.id, u.username)
                              }
                              className="rounded-lg bg-cobalt-600 hover:bg-cobalt-700 p-1.5 text-white cursor-pointer"
                              title="Guardar nueva contraseña"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEditandoPassId(null);
                                setNuevaPassFila("");
                              }}
                              className="rounded-lg border border-slate-200 dark:border-slate-700 p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                              title="Cancelar"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div className="inline-flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              disabled={procesando}
                              onClick={() => {
                                setEditandoPassId(u.id);
                                setNuevaPassFila("");
                              }}
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-dark-elevated hover:bg-slate-100 dark:hover:bg-slate-800 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 dark:text-slate-200 transition-colors cursor-pointer"
                              title="Cambiar contraseña"
                            >
                              <KeyRound className="h-3 w-3 text-cobalt-600 dark:text-cobalt-400" />
                              <span>Contraseña</span>
                            </button>

                            {!esMiCuenta && (
                              <button
                                type="button"
                                disabled={procesando}
                                onClick={() => void alternarEstadoActivo(u)}
                                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition-colors cursor-pointer ${
                                  u.activo
                                    ? "border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/40"
                                    : "border-emerald-200 dark:border-emerald-900/60 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/40"
                                }`}
                              >
                                <span>
                                  {u.activo ? "Desactivar" : "Activar"}
                                </span>
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
