import { test, expect } from "@playwright/test";

test("cerrado inicialmente, teclado, resumen y móvil", async ({ page }, info) => {
  await page.goto("/tests/ui/actividad.html");
  const panel = page.getByTestId("actividad");
  await expect(panel).not.toHaveAttribute("open");
  await page.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(panel).toHaveAttribute("open", "");
  await expect(page.getByText("Resumen del modelo", { exact: true })).toBeVisible();
  await expect(page.getByText("Verificando su ubicación", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: info.outputPath("actividad.png"), fullPage: true });
});

test("parcial no aparece como completado e historial antiguo funciona", async ({ page }) => {
  await page.goto("/tests/ui/actividad.html?caso=parcial&dark");
  await page.locator("summary").click();
  await expect(page.getByText("Actividad con pasos pendientes", { exact: true })).toBeVisible();
  await expect(page.getByText("Pendiente de verificar", { exact: true })).toBeVisible();
  await page.goto("/tests/ui/actividad.html?caso=antiguo");
  await expect(page.getByText("Respuesta anterior sin actividad guardada.")).toBeVisible();
  await expect(page.getByTestId("actividad")).toHaveCount(0);
});

test("reconectar y recargar retoman el job sin reenviar ni duplicar pasos", async ({ page, context }) => {
  let inicios = 0;
  let terminado = false;
  let sinRed = false;
  const actividades = [{ id: "paso-1", tipo: "accion", texto: "Buscando la carpeta", estado: "completado" }, { id: "paso-2", tipo: "accion", texto: "Restaurando la carpeta", estado: "en_curso" }];
  await page.route("**/api/v1/chat/async", r => { inicios++; return r.fulfill({ json: { job_id: "job-estable", status: "running" } }); });
  const snapshot = () => terminado ? { job_id: "job-estable", status: "completed", etapa: "trabajando", actividades: actividades.map(a => ({ ...a, estado: "completado" })), result: { respuesta: "Carpeta restablecida y verificada.", actividades: actividades.map(a => ({ ...a, estado: "completado" })), archivo_almacen_url: null, archivo_txt_url: null, reportes_historicos: [] } } : { job_id: "job-estable", status: "running", etapa: "trabajando", actividades, result: null };
  await page.route("**/api/v1/chat/events/job-estable", r => r.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify(snapshot())}\n\n` }));
  await page.route("**/api/v1/chat/status/job-estable", r => sinRed ? r.abort("internetdisconnected") : r.fulfill({ json: snapshot() }));
  await page.goto("/tests/ui/actividad.html?caso=live");
  await page.getByRole("button", { name: "Enviar solicitud" }).click();
  await expect(page.locator("summary")).toContainText("Restaurando la carpeta");
  const desconectada = page.waitForEvent("requestfailed");
  sinRed = true;
  await context.setOffline(true);
  await desconectada;
  sinRed = false;
  await context.setOffline(false);
  await page.reload();
  await expect(page.locator("summary")).toContainText("Restaurando la carpeta");
  terminado = true;
  await expect(page.getByText("Carpeta restablecida y verificada.")).toBeVisible({ timeout: 15000 });
  expect(inicios).toBe(1);
  await page.locator("summary").click();
  await expect(page.getByText("Buscando la carpeta", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Restaurando la carpeta", { exact: true })).toHaveCount(1);
  expect(await page.evaluate(() => sessionStorage.getItem("flucito_job:prueba-fase4"))).toBeNull();
});

test("error definitivo y recuperación tienen estados distintos", async ({ page }) => {
  await page.goto("/tests/ui/actividad.html?caso=error");
  await page.locator("summary").click();
  await expect(page.getByText("Actividad interrumpida", { exact: true })).toBeVisible();
  await expect(page.getByText("Interrumpido", { exact: true })).toBeVisible();
  await page.goto("/tests/ui/actividad.html?caso=recuperado");
  await page.locator("summary").click();
  await expect(page.getByText("Recuperado tras un reintento", { exact: true })).toBeVisible();
});
