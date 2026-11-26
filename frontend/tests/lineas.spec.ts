import { test, expect } from "@playwright/test";
import type { InteraccionDecision, RevisionReporte } from "../src/schemas/chat";

for (const oscuro of [false, true]) {
  test(`línea sugerida y aviso accesible en tema ${oscuro ? "oscuro" : "claro"}`, async ({ page }, info) => {
    const interaccion: InteraccionDecision = { id: "linea-1", revision: 1, estado: "pendiente", permite_recordar: false, respuestas: {}, preguntas: [{
      id: "linea:BW-SAF4000DME", tipo: "linea", titulo: "BW-SAF4000DME — Vaso metálico para filtro SAF4000 con purga. ¿Qué línea deseas usar?", contexto: { producto: "BW-SAF4000DME" }, clave_preferencia: null,
      opciones: [{ id: "linea:YPC", titulo: "Aplicar línea YPC", descripcion: "BW-SAF4000ME — VASO METALICO PARA SAF4000 SIN PURGA · línea YPC. Factor: YPC. Revisa las diferencias de modelo." },
        { id: "manual", titulo: "Completar línea y precios manualmente en el Excel", descripcion: "Se conserva el costo de compra. La línea y los cinco precios de venta quedan vacíos." }] }] };
    await page.route("**/api/v1/chat/conversaciones/decision-e2e", r => r.fulfill({ json: { id: "decision-e2e", mensajes: [{ id: 1, rol: "assistant", contenido: "Carpeta 20-10-2026: falta confirmar una línea.", creado_en: new Date().toISOString(), interaccion,
      avisos: [{ nivel: "advertencia", titulo: "Línea por confirmar · BW-SAF4000DME", descripcion: "El TXT contiene BW-. El XML aporta BW-SAF4000DME y el catálogo del SAE confirma su clave. La columna de línea está vacía en el TXT y en el catálogo del SAE.", accion: "Confirma la referencia o completa el Excel." }] }] } }));
    await page.route("**/api/v1/chat/conversaciones/decision-e2e/decisiones", r => r.fulfill({ json: { ...interaccion, revision: 2, respuestas: r.request().postDataJSON().respuestas } }));
    await page.goto(`/tests/ui/decisiones.html${oscuro ? "?dark" : ""}`);
    await expect(page.getByRole("status").filter({ hasText: "Línea por confirmar" })).toContainText("La columna de línea está vacía");
    await expect(page.getByRole("paragraph").filter({ hasText: "BW-SAF4000DME — Vaso metálico para filtro SAF4000 con purga." })).toBeVisible();
    await expect(page.getByRole("radio", { name: /^Completar línea y precios manualmente en el Excel/ })).toBeVisible();
    await page.screenshot({ path: info.outputPath(`linea-${oscuro ? "oscuro" : "claro"}.png`), fullPage: true });
    await expect(page.getByRole("button", { name: "Aplicar decisiones y continuar" })).toBeDisabled();
    await page.getByRole("radio", { name: /^Aplicar línea YPC/ }).focus();
    await page.keyboard.press("Space");
    await expect(page.getByRole("button", { name: "Aplicar decisiones y continuar" })).toBeEnabled();
    await expect(page.getByText("Aplicar línea YPC · Cambiar respuesta")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}

test("Excel revisado persiste tras recargar y continúa con la tarjeta de factores", async ({ page }, info) => {
  let interaccion: InteraccionDecision = { id: "factor-revision", revision: 1, estado: "pendiente", permite_recordar: true, respuestas: {}, preguntas: [{ id: "factor:ZZ9", tipo: "factor", titulo: "¿Qué factor deseas aplicar a ZZ9?", contexto: { linea: "ZZ9" }, clave_preferencia: "factor-zz9", opciones: [{ id: "YPC", titulo: "YPC", descripcion: "Completar solo los precios vacíos con el factor YPC." }, { id: "manual", titulo: "Continuar con precios manuales", descripcion: "Conservar los campos pendientes." }] }] };
  let revision: RevisionReporte = { id: "b".repeat(32), nombre: "ENTRADAS_20-10-2026.xlsx", version: 1, estado: "pendiente", pendientes: [{ producto: "BW-SAF4000DME", campos: ["Línea", "PUBLICO", "MINIMO"] }] };
  let ejecuciones = 0;
  await page.route("**/api/v1/chat/conversaciones/decision-e2e", r => r.fulfill({ json: { id: "decision-e2e", mensajes: [{ id: 1, rol: "assistant", contenido: "Revisión de la carpeta 20-10-2026.", creado_en: new Date().toISOString(), revision_reporte: revision }] } }));
  await page.route("**/api/v1/almacen/reportes/*?session_id=*", r => r.fulfill({ json: revision }));
  await page.route("**/api/v1/almacen/reportes/*/validar?session_id=*", r => {
    revision = { ...revision, version: 2, estado: "factor_pendiente", pendientes: [{ producto: "BW-SAF4000DME", campos: ["MINIMO"] }], interaccion, resumen_revision: "La línea ZZ9 quedó guardada. Conservé el precio PUBLICO capturado por el asesor." };
    return r.fulfill({ json: revision });
  });
  await page.route("**/api/v1/chat/conversaciones/decision-e2e/decisiones", r => {
    interaccion = { ...interaccion, revision: interaccion.revision + 1, respuestas: r.request().postDataJSON().respuestas };
    revision = { ...revision, interaccion };
    return r.fulfill({ json: interaccion });
  });
  await page.route("**/api/v1/chat/async", r => {
    ejecuciones++;
    interaccion = { ...interaccion, estado: "aplicada" };
    revision = { ...revision, interaccion, version: 3, estado: "validado", pendientes: [], resumen_revision: "Carpeta 20-10-2026: BW-SAF4000DME, línea ZZ9, factor YPC. Conservé PUBLICO y completé MINIMO. Los TXT están listos." };
    return r.fulfill({ json: { job_id: "revision-job", status: "running" } });
  });
  await page.route("**/api/v1/chat/events/revision-job", r => r.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify({ status: "completed", result: { respuesta: revision.resumen_revision, revision_reporte: revision, interaccion, reportes_historicos: [] } })}\n\n` }));
  await page.goto("/tests/ui/decisiones.html");
  await page.getByLabel("Subir Excel corregido").setInputFiles({ name: "corregido.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("fixture; actual xlsx validated by backend tests") });
  await page.getByRole("button", { name: "Validar y generar TXT" }).click();
  await expect(page.getByText("El Excel revisado está guardado", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("El Excel revisado está guardado", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Descargar TXT/ })).toHaveCount(0);
  await page.getByRole("radio", { name: /^YPC/ }).check();
  await page.screenshot({ path: info.outputPath("excel-factor-pendiente.png"), fullPage: true });
  await page.getByRole("button", { name: "Aplicar decisiones y continuar" }).click();
  await expect(page.getByText("Líneas y precios validados. Los TXT están listos.").first()).toBeVisible();
  expect(ejecuciones).toBe(1);
  await page.screenshot({ path: info.outputPath("excel-validado.png"), fullPage: true });
});
