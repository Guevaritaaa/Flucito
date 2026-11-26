import { test, expect, type Page } from "@playwright/test";
import type { InteraccionDecision, EnvioDecisiones } from "../src/schemas/chat";

async function preparar(page: Page, reporte = false) {
  let interaccion: InteraccionDecision = { id: "preguntas-1", revision: 1, estado: "pendiente", permite_recordar: true, respuestas: {}, preguntas: [
    { id: "factor:DAYCO", tipo: "factor", titulo: "¿Qué factor deseas aplicar a DAYCO?", contexto: { linea: "DAYCO" }, clave_preferencia: "factor", opciones: [
      { id: "FESTO", titulo: "FESTO", descripcion: "PUBLICO: compra / 0.7; MINIMO: compra / 0.9" },
      { id: "custom", titulo: "Crear factor personalizado", descripcion: "Define los cinco precios en una tabla guiada." },
      { id: "manual", titulo: "Dejar precios de venta para llenado manual", descripcion: "Los precios quedarán vacíos." }] },
    { id: "metros:M1", tipo: "metros", titulo: "Manguera M1: ¿deseas dividir el precio entre 20 metros?", contexto: { producto: "M1" }, clave_preferencia: "metros", opciones: [
      { id: "conservar", titulo: "Conservar precio original", descripcion: "Se conservan $600 por rollo." },
      { id: "dividir", titulo: "Dividir precio entre los metros", descripcion: "$600 / 20 = $30 por metro." },
      { id: "manual", titulo: "Dejar precios para llenado manual", descripcion: "Compra y venta quedarán vacíos; el TXT esperará." }] },
  ] };
  let confirmacion: EnvioDecisiones | undefined;
  let inicios = 0;
  const revision = { id: "a".repeat(32), version: 1, nombre: "ENTRADAS.xlsx", estado: "pendiente", pendientes: [{ producto: "M1", campos: ["PUBLICO"] }] };
  await page.route("**/api/v1/chat/conversaciones/decision-e2e", r => r.fulfill({ json: { id: "decision-e2e", mensajes: [{ id: 1, rol: "assistant", contenido: "Revisa tus decisiones.", creado_en: new Date().toISOString(), interaccion: reporte ? null : interaccion, revision_reporte: reporte ? revision : null }] } }));
  await page.route("**/api/v1/chat/conversaciones/decision-e2e/decisiones", async r => {
    const envio = r.request().postDataJSON();
    expect(envio.revision).toBe(interaccion.revision);
    interaccion = { ...interaccion, revision: interaccion.revision + 1, respuestas: envio.respuestas };
    await r.fulfill({ json: interaccion });
  });
  await page.route("**/api/v1/chat/async", async r => { inicios++; confirmacion = r.request().postDataJSON().decisiones; interaccion = { ...interaccion, estado: "aplicada", respuestas: confirmacion!.respuestas }; await r.fulfill({ json: { job_id: "job-decision", status: "running" } }); });
  await page.route("**/api/v1/chat/events/job-decision", r => r.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify({ status: "completed", result: { respuesta: "Decisiones aplicadas.", interaccion, archivo_almacen_url: null, archivo_txt_url: null, reportes_historicos: [] } })}\n\n` }));
  await page.route("**/api/v1/almacen/reportes/*?session_id=*", r => r.fulfill({ json: revision }));
  await page.route("**/api/v1/almacen/reportes/*/validar?session_id=*", r => r.fulfill({ json: { ...revision, version: 2, pendientes: [], estado: "validado" } }));
  return { get interaccion() { return interaccion; }, get confirmacion() { return confirmacion; }, get inicios() { return inicios; } };
}

test("seleccionar, recordar, recargar, cambiar resumen y aplicar una sola vez", async ({ page }, info) => {
  const estado = await preparar(page);
  await page.goto("/tests/ui/decisiones.html");
  await expect(page.getByRole("button", { name: "Aplicar decisiones y continuar" })).toBeDisabled();
  await page.getByRole("radio", { name: /^FESTO/ }).focus();
  await page.keyboard.press("Space");
  await page.getByRole("checkbox", { name: "Recordar esta elección para mi usuario" }).check();
  await page.getByRole("radio", { name: /^Dividir precio entre los metros/ }).check();
  await expect.poll(() => estado.interaccion.respuestas["metros:M1"]?.opcion).toBe("dividir");
  await page.reload();
  await expect(page.getByText("FESTO · Cambiar respuesta")).toBeVisible();
  await page.getByText("Dividir precio entre los metros · Cambiar respuesta").click();
  await page.getByRole("radio", { name: /^Conservar precio original/ }).check();
  await expect(page.getByRole("button", { name: "Aplicar decisiones y continuar" })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: info.outputPath("decisiones.png"), fullPage: true });
  await page.getByRole("button", { name: "Aplicar decisiones y continuar" }).click();
  await expect(page.getByRole("heading", { name: "Decisiones aplicadas" })).toBeVisible();
  expect(estado.confirmacion?.respuestas["metros:M1"].opcion).toBe("conservar");
  expect(estado.confirmacion?.respuestas["factor:DAYCO"].recordar).toBe(true);
  expect(estado.inicios).toBe(1);
});

test("factor guiado, validación y tema oscuro", async ({ page }, info) => {
  await preparar(page);
  await page.goto("/tests/ui/decisiones.html?dark");
  await page.getByRole("radio", { name: /^Crear factor personalizado/ }).check();
  await page.getByRole("textbox", { name: "Nombre del factor" }).fill("Mi factor");
  await page.getByRole("spinbutton", { name: "Valor PUBLICO 1", exact: true }).fill("2");
  await expect(page.getByText("$200.0000", { exact: false })).toBeVisible();
  await page.getByRole("radio", { name: /^Dividir precio entre los metros/ }).check();
  await page.getByRole("spinbutton", { name: "Valor PUBLICO 1", exact: true }).fill("0");
  await expect(page.getByRole("button", { name: "Aplicar decisiones y continuar" })).toBeDisabled();
  await page.getByRole("spinbutton", { name: "Valor PUBLICO 1", exact: true }).fill("2");
  await expect(page.getByRole("button", { name: "Aplicar decisiones y continuar" })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: info.outputPath("factor-oscuro.png"), fullPage: true });
});

test("recarga inmediata conserva selecciones antes del guardado remoto", async ({ page }) => {
  await preparar(page);
  await page.goto("/tests/ui/decisiones.html");
  await page.getByRole("radio", { name: /^FESTO/ }).check();
  await page.reload();
  await expect(page.getByText("FESTO · Cambiar respuesta")).toBeVisible();
});

test("adjuntar Excel corregido habilita TXT solo tras validarlo", async ({ page }) => {
  await preparar(page, true);
  let intentos = 0;
  await page.route("**/api/v1/almacen/reportes/*/validar?session_id=*", r => {
    intentos++;
    return intentos === 1
      ? r.fulfill({ status: 422, json: { detail: { errores: [{ producto: "M1", campo: "PUBLICO", motivo: "Debe ser un número positivo y finito" }] } } })
      : r.fulfill({ json: { id: "a".repeat(32), version: 2, nombre: "ENTRADAS.xlsx", estado: "validado", pendientes: [] } });
  });
  await page.goto("/tests/ui/decisiones.html");
  await expect(page.getByText("La línea y los precios señalados quedarán vacíos para su llenado manual.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /Descargar TXT/ })).toHaveCount(0);
  await page.getByLabel("Subir Excel corregido").setInputFiles({ name: "corregido.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("fixture: validation is exercised in backend tests") });
  await page.getByRole("button", { name: "Validar y generar TXT" }).click();
  await expect(page.getByRole("alert")).toContainText("M1 · PUBLICO");
  await expect(page.getByRole("button", { name: /Descargar TXT/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Validar y generar TXT" }).click();
  await expect(page.getByText("Líneas y precios validados. Los TXT están listos.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Descargar TXT/ })).toHaveCount(2);
});

test("recuperar una confirmación en curso no vuelve a iniciarla", async ({ page }) => {
  const estado = await preparar(page);
  let terminado = false;
  const resultado = () => terminado ? { status: "completed", result: { respuesta: "Decisiones aplicadas.", interaccion: estado.interaccion, archivo_almacen_url: null, archivo_txt_url: null, reportes_historicos: [] } } : { status: "running", etapa: "trabajando" };
  await page.route("**/api/v1/chat/events/job-decision", r => r.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify(resultado())}\n\n` }));
  await page.route("**/api/v1/chat/status/job-decision", r => r.fulfill({ json: resultado() }));
  await page.goto("/tests/ui/decisiones.html");
  await page.getByRole("radio", { name: /^FESTO/ }).check();
  await page.getByRole("radio", { name: /^Dividir precio entre los metros/ }).check();
  await page.getByRole("button", { name: "Aplicar decisiones y continuar" }).click();
  await expect.poll(() => estado.inicios).toBe(1);
  terminado = true;
  await page.reload();
  await expect(page.getByText("Decisiones aplicadas.", { exact: true })).toBeVisible();
  expect(estado.inicios).toBe(1);
  expect(estado.confirmacion?.respuestas["metros:M1"].opcion).toBe("dividir");
});

test("la ronda siguiente solo muestra sus decisiones, incluso al recargar", async ({ page }) => {
  const estado = await preparar(page);
  const texto = "Revisa las siguientes decisiones para continuar.";
  const siguiente = (): InteraccionDecision => ({
    id: "preguntas-2", revision: 1, estado: "pendiente", permite_recordar: false, respuestas: {},
    anteriores: [estado.interaccion],
    preguntas: [{ id: "linea:P1", tipo: "linea", titulo: "P1 — Vaso metálico. ¿Qué línea deseas usar?",
      contexto: { producto: "P1" }, clave_preferencia: null,
      opciones: [{ id: "manual", titulo: "Completar línea y precios manualmente en el Excel", descripcion: "Conserva el costo de compra." }] }],
  });
  await page.route("**/api/v1/chat/conversaciones/decision-e2e", r => {
    const creado_en = new Date().toISOString();
    const mensajes = [{ id: 1, rol: "assistant", contenido: texto, creado_en, interaccion: estado.interaccion }];
    if (estado.confirmacion) mensajes.push({ id: 2, rol: "assistant", contenido: texto, creado_en, interaccion: siguiente() });
    return r.fulfill({ json: { id: "decision-e2e", mensajes } });
  });
  await page.route("**/api/v1/chat/events/job-decision", r => r.fulfill({ contentType: "text/event-stream",
    body: `data: ${JSON.stringify({ status: "completed", result: { respuesta: texto, interaccion: siguiente() } })}\n\n` }));

  await page.goto("/tests/ui/decisiones.html");
  await page.getByRole("radio", { name: /^FESTO/ }).check();
  await page.getByRole("radio", { name: /^Dividir precio entre los metros/ }).check();
  await page.getByRole("button", { name: "Aplicar decisiones y continuar" }).click();

  const mensajes = page.locator('[data-role="assistant-message"]');
  for (const recargar of [false, true]) {
    if (recargar) await page.reload();
    await expect(mensajes).toHaveCount(2);
    await expect(mensajes.first().getByRole("heading", { name: "Decisiones aplicadas" })).toBeVisible();
    await expect(mensajes.first().getByText("FESTO · Ver respuesta")).toBeVisible();
    await expect(mensajes.first().getByRole("button", { name: "Aplicar decisiones y continuar" })).toHaveCount(0);
    await expect(mensajes.last().getByRole("radio", { name: /^Completar línea y precios manualmente/ })).toBeVisible();
    await expect(mensajes.last().getByText("DAYCO", { exact: false })).toHaveCount(0);
    await expect(mensajes.last().getByText("Ver decisiones anteriores")).toHaveCount(0);
  }
});
