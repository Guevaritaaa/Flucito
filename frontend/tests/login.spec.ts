import { test, expect } from "@playwright/test";

for (const cuenta of [
  { username: "xroberthz", nombre_completo: "xroberthz", rol: "admin" },
  { username: "jose", nombre_completo: "Jose", rol: "operador" },
]) {
  test(`cada login y sesión restaurada abren Inicio para ${cuenta.username}`, async ({ page }, info) => {
    const usuario = { ...cuenta, id: 1, activo: true, creado_en: "2026-11-23T00:00:00Z" };
    await page.route("**/api/v1/**", route => {
      const ruta = new URL(route.request().url()).pathname;
      if (ruta === "/api/v1/auth/login") {
        return route.fulfill({ json: { access_token: "token-prueba", token_type: "bearer", usuario } });
      }
      if (ruta === "/api/v1/auth/me") return route.fulfill({ json: usuario });
      return route.fulfill({ json: [] });
    });
    await page.goto("/");
    const entrar = async () => {
      await page.locator("#login-username").fill(cuenta.username);
      await page.locator("#login-password").fill("clave-de-prueba");
      await page.getByRole("button", { name: "Entrar", exact: true }).click();
      await expect(page.locator("#tab-inicio-content")).toBeVisible();
      await expect(page.getByRole("heading", { name: `¡Bienvenido, ${cuenta.nombre_completo}!` })).toBeVisible();
    };
    await entrar();
    if (info.project.name === "mobile") {
      await page.getByRole("button", { name: "Mostrar barra lateral" }).click();
    }
    await expect(page.locator("#sidebar").getByText(cuenta.nombre_completo, { exact: true })).toBeVisible();
    await expect(page.locator("#sidebar").getByText(cuenta.rol, { exact: true })).toHaveCount(0);
    await page.screenshot({ path: info.outputPath("inicio.png"), fullPage: true });
    await page.locator("#sidebar").getByRole("button", { name: "Nuevo chat", exact: true }).click();
    await expect(page.locator("#tab-inicio-content")).toHaveCount(0);
    if (info.project.name === "mobile") {
      await page.getByRole("button", { name: "Mostrar barra lateral" }).click();
    }
    await page.getByRole("button", { name: "Cerrar sesión" }).click();
    await entrar();
    await page.reload();
    await expect(page.locator("#tab-inicio-content")).toBeVisible();
  });
}
