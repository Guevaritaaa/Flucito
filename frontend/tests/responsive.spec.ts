import { expect, test, type Locator, type Page } from "@playwright/test";

test.use({ reducedMotion: "reduce" });

const usuario = {
  id: 1,
  username: "robert",
  nombre_completo: "Robert Hernández (Administrador de Interflu)",
  rol: "admin",
  activo: true,
  creado_en: "2026-11-23T00:00:00Z",
};

const respuesta = "Respuesta de Flucito para comprobar el historial.";

async function simularApi(page: Page) {
  await page.route("**/api/v1/**", (route) => {
    const ruta = new URL(route.request().url()).pathname;
    switch (ruta) {
      case "/api/v1/auth/login":
        return route.fulfill({ json: { access_token: "token-prueba", token_type: "bearer", usuario } });
      case "/api/v1/auth/me":
        return route.fulfill({ json: usuario });
      case "/api/v1/chat/async":
        return route.fulfill({ json: { job_id: "responsive", status: "running" } });
      case "/api/v1/chat/events/responsive":
        return route.fulfill({
          contentType: "text/event-stream",
          body: "data: " + JSON.stringify({
            job_id: "responsive",
            status: "completed",
            result: {
              respuesta: Array(20).fill(respuesta).join("\n\n"),
              actividades: [],
              reportes_historicos: [],
            },
          }) + "\n\n",
        });
      default:
        return route.fulfill({ json: [] });
    }
  });
}

async function entrar(page: Page) {
  await page.getByLabel("Usuario", { exact: true }).fill(usuario.username);
  await page.locator("#login-password").fill("clave-de-prueba");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Bienvenido, Robert/ })).toBeVisible();
}

async function cabeEnAncho(locator: Locator) {
  expect(await locator.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
}

for (const [width, height] of [[320, 480], [360, 560], [390, 640]]) {
  test("acceso e Inicio son recorribles a " + width + " px", async ({ page, isMobile }, info) => {
    test.skip(!isMobile, "Prueba de distribución móvil");
    await page.setViewportSize({ width, height });
    await simularApi(page);
    await page.goto("/");

    const acceso = page.getByRole("main");
    await expect(acceso.getByRole("img", { name: /^Interflu/ })).toBeInViewport({ ratio: 1 });
    await expect(acceso.getByRole("button", { name: "Activar modo oscuro" })).toBeInViewport({ ratio: 1 });
    await expect(page.getByLabel("Usuario", { exact: true })).not.toBeFocused();
    await cabeEnAncho(acceso);
    await cabeEnAncho(page.locator("html"));
    await page.screenshot({ path: info.outputPath("acceso-claro.png"), animations: "disabled" });
    await page.getByRole("button", { name: "Activar modo oscuro" }).tap();
    await page.screenshot({ path: info.outputPath("acceso-oscuro.png"), animations: "disabled" });

    const mascota = acceso.getByRole("img", { name: /Mascota Oficial/ });
    await mascota.scrollIntoViewIfNeeded();
    await expect(mascota).toBeInViewport({ ratio: 0.99 });
    await acceso.getByRole("button", { name: "Solicitar acceso" }).tap();
    await expect(acceso.getByRole("status")).toContainText(/cuentas son asignadas/);
    await entrar(page);

    const inicio = page.getByRole("main");
    const avatar = inicio.getByRole("img", { name: "Flucito", exact: true }).locator("..");
    const nuevo = inicio.getByRole("button", { name: "Nueva conversación" });
    await expect(avatar).toBeInViewport({ ratio: 1 });
    await expect(nuevo).toBeInViewport({ ratio: 1 });
    await cabeEnAncho(inicio);
    await cabeEnAncho(page.locator("html"));
    await page.screenshot({ path: info.outputPath("inicio-oscuro.png"), animations: "disabled" });
    await page.getByRole("button", { name: "Activar modo claro" }).tap();
    await page.screenshot({ path: info.outputPath("inicio-claro.png"), animations: "disabled" });
    const final = inicio.getByText(/Genera reportes de almacén/);
    await final.scrollIntoViewIfNeeded();
    await expect(final).toBeInViewport({ ratio: 1 });

    await page.getByRole("button", { name: "Mostrar barra lateral" }).tap();
    const sidebar = page.getByRole("complementary");
    await cabeEnAncho(sidebar);
    await sidebar.getByRole("button", { name: "Configuración" }).tap();
    await cabeEnAncho(page.getByRole("main"));
    await page.getByLabel("Idioma del Asistente").scrollIntoViewIfNeeded();
    await expect(page.getByLabel("Idioma del Asistente")).toBeInViewport();
  });
}

for (const pantalla of [
  { nombre: "vertical", width: 390, height: 640, alturaReducida: 320 },
  { nombre: "horizontal", width: 740, height: 340, alturaReducida: 210 },
]) {
  test("el compositor permanece accesible en " + pantalla.nombre, async ({ page, isMobile }) => {
    test.skip(!isMobile, "Prueba del teclado en distribución móvil");
    const { width, height, alturaReducida } = pantalla;
    await page.setViewportSize({ width, height });
    await simularApi(page);
    await page.goto("/");
    await entrar(page);

    await page.getByRole("button", { name: "Nueva conversación" }).tap();
    const campo = page.getByRole("textbox", { name: "Mensaje para Flucito" });
    const enviar = page.getByRole("button", { name: "Enviar mensaje" });
    await expect(campo).not.toBeFocused();
    await campo.tap();
    await page.setViewportSize({ width, height: alturaReducida });
    await expect(page.locator("#root")).toHaveCSS("height", alturaReducida + "px");
    await campo.fill("Primer mensaje");
    await expect(campo).toBeInViewport({ ratio: 0.99 });
    await expect(enviar).toBeInViewport({ ratio: 0.99 });
    await enviar.tap();

    const historial = page.locator("[data-purpose='message-history']");
    await expect(historial.getByText(respuesta, { exact: true })).toHaveCount(20);
    await cabeEnAncho(historial);
    await historial.getByText(respuesta, { exact: true }).first().scrollIntoViewIfNeeded();
    await expect(historial.getByText(respuesta, { exact: true }).first()).toBeInViewport();
    await campo.tap();
    await campo.fill("Segundo mensaje\n".repeat(15));
    await expect(campo).toBeInViewport({ ratio: 1 });
    await expect(enviar).toBeInViewport({ ratio: 1 });
  });
}

test("el acceso y el inicio conservan la distribución de escritorio", async ({ page, isMobile }, info) => {
  test.skip(isMobile, "Prueba de distribución de escritorio");
  await simularApi(page);
  await page.goto("/");
  const acceso = page.getByRole("main");
  const logo = acceso.getByRole("img", { name: /^Interflu/ });
  const mascota = acceso.getByRole("img", { name: /Mascota Oficial/ });
  await expect(logo).toBeInViewport({ ratio: 0.99 });
  await expect(mascota).toBeInViewport({ ratio: 0.99 });
  expect((await mascota.boundingBox())!.x).toBeGreaterThan((await logo.boundingBox())!.x);
  await page.screenshot({ path: info.outputPath("acceso-claro.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Activar modo oscuro" }).click();
  await page.screenshot({ path: info.outputPath("acceso-oscuro.png"), animations: "disabled" });
  await entrar(page);

  const inicio = page.getByRole("main");
  const acciones = inicio.getByRole("button", { name: "Nueva conversaci\u00f3n" });
  const catalogo = inicio.getByText("Cat\u00e1logo Aspel SAE", { exact: true });
  expect((await acciones.boundingBox())!.y).toBeGreaterThan((await catalogo.boundingBox())!.y);
  await page.screenshot({ path: info.outputPath("inicio-oscuro.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Activar modo claro" }).click();
  await page.screenshot({ path: info.outputPath("inicio-claro.png"), animations: "disabled" });
});
