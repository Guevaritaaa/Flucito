import { useEffect, useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { PRECIOS_FACTOR, type CamposDecision, type EnvioDecisiones, type InteraccionDecision, type PrecioFactor, type RespuestaDecision, type RevisionReporte } from "../../schemas/chat";
import { apiFetch } from "../../services/http";
import { descargarArchivo } from "../../services/almacenService";

const control = "rounded-lg border border-slate-400 bg-white p-2 text-sm text-slate-900 focus-visible:outline-2 focus-visible:outline-blue-600 dark:border-slate-500 dark:bg-slate-900 dark:text-white disabled:opacity-60";
const boton = "rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:opacity-50";

function factorInicial(): CamposDecision {
  return { nombre: "", precios: Object.fromEntries(PRECIOS_FACTOR.map(p => [p, { base: "COSTEO", pasos: [{ operacion: "*", valor: 1 }] }])) as CamposDecision["precios"] };
}

function calcular(campos: CamposDecision, precio: PrecioFactor, compra = 100): number {
  const fila = campos.precios?.[precio];
  if (!fila) return NaN;
  let valor = fila.base === "PUBLICO" ? calcular(campos, "PUBLICO", compra) : compra;
  for (const paso of fila.pasos) {
    const n = Number(paso.valor);
    if (!Number.isFinite(n) || n <= 0) return NaN;
    valor = paso.operacion === "*" ? valor * n : valor / n;
  }
  return valor;
}

function FactorEditor({ campos, onChange, disabled }: { campos: CamposDecision; onChange: (c: CamposDecision) => void; disabled: boolean }) {
  const valores = campos.precios ? campos : factorInicial();
  function fila(precio: PrecioFactor, cambio: Partial<NonNullable<CamposDecision["precios"]>[PrecioFactor]>) {
    onChange({ ...valores, precios: { ...valores.precios!, [precio]: { ...valores.precios![precio], ...cambio } } });
  }
  return <fieldset disabled={disabled} className="mt-3 min-w-0 space-y-4">
    <label className="grid min-w-0 gap-1 text-sm">Nombre del factor<input className={`${control} min-w-0 w-full`} maxLength={80} value={valores.nombre ?? ""} onChange={e => onChange({ ...valores, nombre: e.target.value })} /></label>
    <p className="text-xs">Vista previa con un precio de compra de $100.00. Cada paso se aplica de izquierda a derecha.</p>
    <div className="max-w-full overflow-x-auto"><table className="block w-full text-left text-sm sm:table"><caption className="sr-only">Fórmulas de los cinco precios de venta</caption><thead className="hidden sm:table-header-group"><tr><th className="p-2">Precio</th><th className="p-2">Base y operaciones</th><th className="p-2">Resultado</th></tr></thead><tbody className="block sm:table-row-group">
      {PRECIOS_FACTOR.map(p => <tr key={p} className="block border-t border-slate-300 sm:table-row dark:border-slate-600">
        <th scope="row" className="block p-2 align-top text-xs sm:table-cell">{p}</th>
        <td className="block space-y-2 p-2 sm:table-cell"><select aria-label={`Base ${p}`} className={control} value={valores.precios![p].base} onChange={e => fila(p, { base: e.target.value as "COSTEO" | "PUBLICO" })}><option value="COSTEO">Compra</option>{p !== "PUBLICO" && <option value="PUBLICO">Público</option>}</select>
          {valores.precios![p].pasos.map((paso, n) => <div key={n} className="flex flex-wrap items-center gap-1">
            <select aria-label={`Operación ${p} ${n + 1}`} className={control} value={paso.operacion} onChange={e => fila(p, { pasos: valores.precios![p].pasos.map((v, i) => i === n ? { ...v, operacion: e.target.value as "*" | "/" } : v) })}><option value="*">Multiplicar</option><option value="/">Dividir</option></select>
            <input aria-label={`Valor ${p} ${n + 1}`} className={`${control} w-24`} type="number" min="0.000001" step="any" value={paso.valor} onChange={e => fila(p, { pasos: valores.precios![p].pasos.map((v, i) => i === n ? { ...v, valor: e.target.value } : v) })} />
            <button type="button" className="rounded p-2 hover:bg-slate-200 focus-visible:outline-2 dark:hover:bg-slate-700" aria-label={`Quitar paso ${p} ${n + 1}`} onClick={() => fila(p, { pasos: valores.precios![p].pasos.filter((_, i) => i !== n) })}><Trash2 size={16} /></button>
          </div>)}
          <button type="button" disabled={valores.precios![p].pasos.length >= 12} className="flex items-center gap-1 rounded py-1 text-xs underline underline-offset-4 focus-visible:outline-2" onClick={() => fila(p, { pasos: [...valores.precios![p].pasos, { operacion: "*", valor: 1 }] })}><Plus size={14} />Agregar paso</button>
        </td><td className="block p-2 align-top tabular-nums sm:table-cell"><span className="sm:hidden">Resultado: </span>{Number.isFinite(calcular(valores, p)) ? `$${calcular(valores, p).toFixed(4)}` : "Revisa los valores"}</td>
      </tr>)}
    </tbody></table></div>
  </fieldset>;
}

export function DecisionCard({ interaccion, sessionId, onEnviar, ocupado = false }: { interaccion: InteraccionDecision; sessionId: string; onEnviar: (texto: string, envio: EnvioDecisiones) => Promise<void>; ocupado?: boolean }) {
  const claveLocal = `flucito_decisiones:${sessionId}:${interaccion.id}`;
  function recuperar() {
    try {
      const local = JSON.parse(sessionStorage.getItem(claveLocal) ?? "null");
      if (interaccion.estado === "pendiente" && local?.revision === interaccion.revision) return local.respuestas as Record<string, RespuestaDecision>;
    } catch { /* El servidor sigue siendo la fuente de verdad. */ }
    return interaccion.respuestas;
  }
  const [respuestas, setRespuestas] = useState(recuperar);
  const [estado, setEstado] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const revision = useRef(interaccion.revision);
  const cola = useRef<Promise<void>>(Promise.resolve());
  const respuestasRef = useRef(respuestas);
  const inicial = useRef(true);
  const pendiente = interaccion.estado === "pendiente";
  const disabled = !pendiente || ocupado || enviando;

  useEffect(() => { const valor = recuperar(); revision.current = interaccion.revision; setRespuestas(valor); respuestasRef.current = valor; inicial.current = JSON.stringify(valor) === JSON.stringify(interaccion.respuestas); }, [interaccion.id, interaccion.revision, interaccion.respuestas]);

  function respaldo(valor: Record<string, RespuestaDecision>) {
    try { sessionStorage.setItem(claveLocal, JSON.stringify({ revision: revision.current, respuestas: valor })); } catch { /* Puede continuar con el guardado remoto. */ }
  }

  function guardar(valor: Record<string, RespuestaDecision>) {
    const operacion = cola.current.catch(() => {}).then(async () => {
      setEstado("Guardando…");
      const resultado = await apiFetch<InteraccionDecision>(`/chat/conversaciones/${encodeURIComponent(sessionId)}/decisiones`, { method: "PUT", body: { interaccion_id: interaccion.id, revision: revision.current, respuestas: valor, accion: "borrador" } });
      revision.current = resultado.revision;
      respaldo(respuestasRef.current);
      setEstado("Borrador guardado");
      setError("");
    });
    cola.current = operacion;
    return operacion;
  }
  useEffect(() => {
    if (inicial.current) { inicial.current = false; return; }
    if (!pendiente || enviando) return;
    const timer = window.setTimeout(() => void guardar(respuestas).catch(e => { setEstado(""); setError(e.message); }), 450);
    return () => window.clearTimeout(timer);
    // La revisión se mantiene en la cola de guardado, sin reprogramar el efecto.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [respuestas, enviando, pendiente]);

  function cambiar(id: string, r: RespuestaDecision) {
    const nuevas = { ...respuestasRef.current, [id]: r };
    if (id.startsWith("metros:") && r.opcion === "manual") {
      const unidad = "unidad:" + id.slice(7);
      if (interaccion.preguntas.some(p => p.id === unidad)) nuevas[unidad] = { opcion: "conservar", recordar: nuevas[unidad]?.recordar ?? false, campos: {} };
    }
    respuestasRef.current = nuevas;
    respaldo(nuevas);
    setRespuestas(nuevas);
  }
  const completas = interaccion.preguntas.every(p => {
    const r = respuestas[p.id];
    if (!r) return false;
    if (r.opcion === "custom") return Boolean(r.campos.nombre?.trim()) && PRECIOS_FACTOR.every(p => Number.isFinite(calcular(r.campos, p)) && calcular(r.campos, p) > 0);
    return r.opcion !== "otra_ruta" || Boolean(r.campos.ruta?.trim());
  });
  async function aplicar(accion: "confirmar" | "cancelar") {
    setEnviando(true); setError("");
    try {
      await guardar(respuestasRef.current);
      await onEnviar(accion === "confirmar" ? "Aplicar decisiones y continuar" : "Cancelar operación", { interaccion_id: interaccion.id, revision: revision.current, respuestas: respuestasRef.current, accion });
      try { sessionStorage.removeItem(claveLocal); } catch { /* La operación ya fue confirmada. */ }
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudieron enviar las decisiones."); }
    finally { setEnviando(false); }
  }
  return <section aria-label="Decisiones de Flucito" className="space-y-4 border-t border-slate-300 pt-4 dark:border-slate-600">
    <h3 className="text-base font-semibold">{pendiente ? "Revisa tus decisiones" : interaccion.estado === "aplicada" ? "Decisiones aplicadas" : interaccion.estado === "cancelada" ? "Operación cancelada" : interaccion.estado === "error" ? "Operación interrumpida" : "Aplicando decisiones"}</h3>
    {interaccion.anteriores?.filter(a => a.preguntas.some(p => !interaccion.preguntas.some(actual => actual.id === p.id))).map(a => <details key={a.id}><summary className="cursor-pointer text-sm underline">Ver decisiones anteriores</summary><DecisionCard interaccion={a} sessionId={sessionId} onEnviar={onEnviar} ocupado /></details>)}
    {interaccion.preguntas.map(p => {
      const r = respuestas[p.id];
      const elegida = p.opciones.find(o => o.id === r?.opcion);
      const unidadManual = p.tipo === "unidad" && respuestas["metros:" + p.id.slice(7)]?.opcion === "manual";
      return <div key={p.id} className="border-b border-slate-200 pb-4 dark:border-slate-700">
        <p className="mb-2 text-sm font-semibold">{p.titulo}</p>
        {p.recordada && <p className="mb-2 text-xs text-blue-800 dark:text-sky-200">Elección recuperada de tus preferencias</p>}
        <details open={!r || r.opcion === "custom" || r.opcion === "otra_ruta"}>
          <summary className="cursor-pointer rounded text-sm focus-visible:outline-2">{r ? `${elegida?.titulo ?? "Selección"} · ${pendiente ? "Cambiar respuesta" : "Ver respuesta"}` : "Elegir una opción"}</summary>
          <fieldset disabled={disabled || unidadManual} className="mt-3 min-w-0 space-y-2"><legend className="sr-only">{p.titulo}</legend>
            {p.opciones.map(o => <label key={o.id} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${r?.opcion === o.id ? "border-blue-600 bg-blue-50 dark:bg-blue-950" : "border-slate-300 hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-800"}`}>
              <input className="mt-1 accent-blue-700" type="radio" name={`${interaccion.id}:${p.id}`} checked={r?.opcion === o.id} onChange={() => cambiar(p.id, { opcion: o.id, recordar: r?.recordar ?? false, campos: r?.campos ?? (o.id === "custom" ? factorInicial() : {}) })} />
              <span className="min-w-0"><span className="block text-sm font-medium">{o.titulo}</span><span className="mt-1 block break-words text-xs leading-relaxed text-slate-700 dark:text-slate-200">{o.descripcion}</span></span>
            </label>)}
          </fieldset>
          {r?.opcion === "custom" && <FactorEditor campos={r.campos} disabled={disabled} onChange={campos => cambiar(p.id, { ...r, campos })} />}
          {r?.opcion === "otra_ruta" && <label className="mt-3 grid gap-1 text-sm">Ruta completa o id:ID<input disabled={disabled} className={control} value={r.campos.ruta ?? ""} onChange={e => cambiar(p.id, { ...r, campos: { ruta: e.target.value } })} /></label>}
        </details>
        {unidadManual && <p className="mt-2 text-xs">El llenado manual conserva la unidad original.</p>}
        {r && <p className="mt-2 text-xs leading-relaxed">{elegida?.descripcion}{r.opcion === "custom" && r.campos.nombre ? ` Nombre: ${r.campos.nombre}.` : ""}</p>}
        {r && p.clave_preferencia && interaccion.permite_recordar && <label className="mt-3 flex items-center gap-2 text-xs"><input disabled={disabled} type="checkbox" className="accent-blue-700" checked={r.recordar} onChange={e => cambiar(p.id, { ...r, recordar: e.target.checked })} />Recordar esta elección para mi usuario</label>}
      </div>;
    })}
    {error && <p role="alert" className="whitespace-pre-wrap text-sm text-red-700 dark:text-red-300">{error}</p>}
    {pendiente && <><p role="status" aria-live="polite" className="text-xs">{estado || "Tus selecciones se guardan como borrador. Se aplicarán cuando confirmes."}</p><div className="flex flex-wrap gap-2"><button type="button" className={boton} disabled={disabled || !completas} onClick={() => void aplicar("confirmar")}>{enviando ? "Enviando…" : "Aplicar decisiones y continuar"}</button><button type="button" className={control} disabled={disabled} onClick={() => void aplicar("cancelar")}>Cancelar operación</button></div></>}
  </section>;
}

export function ReportRevisionCard({ reporte, sessionId }: { reporte: RevisionReporte; sessionId: string }) {
  const [actual, setActual] = useState(reporte);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const prefijo = `/almacen/reportes/${reporte.id}`;
  useEffect(() => { void apiFetch<RevisionReporte>(`${prefijo}?session_id=${encodeURIComponent(sessionId)}`).then(setActual).catch(e => setError(e.message)); }, [prefijo, sessionId]);
  async function descargar(formato: string) {
    setOcupado(true); setError("");
    try { await descargarArchivo(`/api/v1${prefijo}/archivo?session_id=${encodeURIComponent(sessionId)}&formato=${formato}`, formato === "xlsx" ? actual.nombre : `ENTRADAS_${formato}.txt`); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo descargar el reporte."); }
    finally { setOcupado(false); }
  }
  async function validar() {
    if (!archivo) return;
    setOcupado(true); setError("");
    try {
      const form = new FormData(); form.append("archivo", archivo);
      setActual(await apiFetch<RevisionReporte>(`${prefijo}/validar?session_id=${encodeURIComponent(sessionId)}`, { method: "POST", body: form }));
      setArchivo(null);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo validar el reporte."); }
    finally { setOcupado(false); }
  }
  return <section aria-label="Revisión de precios del reporte" className="space-y-3 border-t border-slate-300 pt-4 dark:border-slate-600">
    <h3 className="break-words text-sm font-semibold">{actual.nombre} · Versión {actual.version}</h3>
    {actual.pendientes.length > 0 ? <><p className="text-sm">Los precios quedarán vacíos para su llenado manual. En cuanto los rellenes, avísame para validar el reporte y generar el TXT.</p><details><summary className="cursor-pointer text-sm">Ver productos pendientes ({actual.pendientes.length})</summary><ul className="mt-2 space-y-1 text-xs">{actual.pendientes.map(p => <li key={p.producto}>{p.producto}: {p.campos.join(", ")}</li>)}</ul></details></> : <p role="status" className="text-sm">Precios validados. Los TXT están listos.</p>}
    <div className="flex flex-wrap gap-2"><button type="button" className={control} disabled={ocupado} onClick={() => void descargar("xlsx")}>Descargar Excel {actual.pendientes.length ? "para llenar" : "validado"}</button>{!actual.pendientes.length && ["comas", "tabs"].map(f => <button key={f} type="button" className={boton} disabled={ocupado} onClick={() => void descargar(f)}>Descargar TXT ({f === "tabs" ? "tabulaciones" : f})</button>)}</div>
    {!!actual.pendientes.length && <><label className="grid gap-2 text-sm">Subir Excel corregido<input disabled={ocupado} type="file" accept=".xlsx" className={`${control} max-w-full`} onChange={e => setArchivo(e.target.files?.[0] ?? null)} /></label><p className="text-xs">Completa los precios y conserva los productos y las demás columnas. Para los precios que corrijas, usa valores numéricos.</p><button type="button" className={boton} disabled={ocupado || !archivo} onClick={() => void validar()}>{ocupado ? "Validando…" : "Validar y generar TXT"}</button></>}
    {error && <p role="alert" className="whitespace-pre-wrap text-sm text-red-700 dark:text-red-300">{error}</p>}
  </section>;
}
