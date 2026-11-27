import { expect, test } from "@playwright/test";

test("el administrador puede cambiar su acceso SAE y el de un operador", async ({ page, isMobile }) => {
  const datosCuenta = { activo: true, acceso_sae: false, ultimo_login: null, creado_en: "2026-11-26T00:00:00Z" };
  const admin = { ...datosCuenta, id: 1, username: "admin", nombre_completo: "Administradora", rol: "admin" };
  const operador = { ...datosCuenta, id: 2, username: "operador", nombre_completo: "Operador", rol: "operador" };

  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/login")) {
      return route.fulfill({ json: { access_token: "token-prueba", token_type: "bearer", usuario: admin } });
    }
    if (path.endsWith("/auth/me")) return route.fulfill({ json: admin });
    if (path.endsWith("/auth/usuarios")) return route.fulfill({ json: [admin, operador] });
    if (route.request().method() === "PATCH" && /\/auth\/usuarios\/[12]$/.test(path)) {
      const usuario = path.endsWith("/1") ? admin : operador;
      usuario.acceso_sae = route.request().postDataJSON().acceso_sae;
      return route.fulfill({ json: usuario });
    }
    return route.fulfill({ json: [] });
  });

  await page.goto("/");
  await page.locator("#login-username").fill("admin");
  await page.locator("#login-password").fill("clave-de-prueba");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  if (isMobile) await page.getByRole("button", { name: "Mostrar barra lateral" }).click();
  await page.locator("#sidebar").getByRole("button", { name: "Configuración" }).click();

  for (const username of ["operador", "admin"]) {
    const acceso = page.getByRole("switch", { name: `Acceso a Aspel SAE para @${username}` });
    await expect(acceso).toHaveAttribute("aria-checked", "false");
    await acceso.click();
    await expect(acceso).toHaveAttribute("aria-checked", "true");
    await acceso.click();
    await expect(acceso).toHaveAttribute("aria-checked", "false");
  }
});
