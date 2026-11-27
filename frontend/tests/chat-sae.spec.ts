import { expect, test } from "@playwright/test";

test("traslada la pregunta a un chat SAE y oculta sus cifras al retirar el permiso", async ({ page, isMobile }) => {
  const pregunta = "¿Cuántas compras tuvimos en Aspel SAE en junio de 2026?";
  const mensajeRedireccion = "Para consultar Aspel SAE, abre una conversación de SAE.";
  const respuestaSae = "Junio de 2026 tuvo 146 compras.";
  const mensajeBloqueo = "Ya no cuentas con acceso a este chat. Pide acceso a administración para volver a usar Aspel SAE.";
  const cuenta = { id: 1, username: "admin", nombre_completo: "Admin", rol: "admin", activo: true, acceso_sae: true };
  const creada_en = "2026-11-26T00:00:00Z";
  const fechas = { creada_en, actualizada_en: creada_en };
  const diario = { id: "chat-cotidiano", titulo: "Conversación cotidiana", tipo: "general", total_mensajes: 1, ...fechas };
  const sae = { id: "sae-prueba", titulo: "SAE · Compras junio", tipo: "sae", total_mensajes: 0, ...fechas };
  const mensajesDiario = [{ id: 1, rol: "user", contenido: "Mensaje cotidiano anterior", creado_en: creada_en }];
  let segundoChat = false;
  let enviosSae = 0;

  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "token-prueba", usuario: cuenta } });
    if (path.endsWith("/auth/me")) return route.fulfill({ json: cuenta });
    if (path.endsWith("/chat/conversaciones/sae")) {
      segundoChat = true;
      return route.fulfill({ status: 201, json: sae });
    }
    if (path.endsWith("/chat/conversaciones")) {
      const historial = [diario, ...(segundoChat ? [{ ...sae, titulo: cuenta.acceso_sae ? sae.titulo : "Chat de Aspel SAE", bloqueada: !cuenta.acceso_sae }] : [])];
      return route.fulfill({ json: historial });
    }
    if (path.endsWith(diario.id)) return route.fulfill({ json: { ...diario, mensajes: mensajesDiario } });
    if (path.endsWith(sae.id)) return route.fulfill({ json: { ...sae, mensajes: [] } });
    if (path.endsWith("/chat/async")) return route.fulfill({ status: 405 });
    if (path.endsWith("/chat")) {
      const body = route.request().postDataJSON();
      if (body.session_id === sae.id) {
        expect(body.mensaje).toBe(pregunta);
        enviosSae += 1;
        return route.fulfill({ json: { respuesta: respuestaSae } });
      }
      return route.fulfill({ json: { respuesta: mensajeRedireccion, sugerir_chat_sae: true } });
    }
    return route.fulfill({ json: [] });
  });

  await page.goto("/");
  await page.locator("#login-username").fill("admin");
  await page.locator("#login-password").fill("clave-de-prueba");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  const sidebar = page.locator("#sidebar");
  const abrirSidebar = async () => {
    if (isMobile) await page.getByRole("button", { name: "Mostrar barra lateral" }).click();
  };
  await abrirSidebar();
  await sidebar.getByRole("button", { name: /^Conversación cotidiana/ }).click();
  await expect(page.getByText("Mensaje cotidiano anterior", { exact: true })).toBeVisible();
  const editor = page.getByRole("textbox", { name: "Mensaje para Flucito" });
  await editor.fill(pregunta);
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(page.getByText(mensajeRedireccion, { exact: true })).toBeVisible();
  await page.locator("main").getByRole("button", { name: "Abrir chat SAE" }).click();
  await expect(editor).toHaveValue(pregunta);
  await expect(page).toHaveURL(/chat=sae-prueba/);
  expect(enviosSae).toBe(0);
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(page.getByText(respuestaSae, { exact: true })).toBeVisible();

  cuenta.acceso_sae = false;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByText(mensajeBloqueo, { exact: true })).toBeVisible();
  await expect(page.getByText(respuestaSae, { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(mensajeBloqueo, { exact: true })).toBeVisible();

  await abrirSidebar();
  const bloqueado = sidebar.getByRole("button", { name: "Chat de Aspel SAE" });
  await expect(bloqueado).toHaveAttribute("aria-disabled", "true");
  const nuevo = sidebar.getByRole("button", { name: "Abrir chat SAE" });
  await expect(nuevo).toHaveAttribute("aria-disabled", "true");
  await nuevo.focus();
  const aviso = sidebar.getByRole("tooltip");
  await expect(aviso).toBeVisible();
  await expect(aviso).toHaveText("Para usar Aspel SAE, pide acceso a administración.");
  await sidebar.getByRole("button", { name: /^Conversación cotidiana/ }).click();
  await expect(page.getByText("Mensaje cotidiano anterior", { exact: true })).toBeVisible();
});
