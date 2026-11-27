import { expect, test, type Page } from "@playwright/test";
import type { ResumenComprasSae } from "../src/schemas/sae";

const usuario = { id: 1, username: "admin", nombre_completo: "Admin", rol: "admin", activo: true, acceso_sae: true };
const corte = { corte_id: "empresa02-prueba", empresa: "02", fecha_respaldo: null, cobertura: { desde: "2023-10-22", hasta: "2026-07-01" } };
const mxn = { moneda: "MXN", documentos: 141, importe: "183417.35" };
const usd = { moneda: "USD", documentos: 5, importe: "2345.67" };
const junio: ResumenComprasSae = {
  corte,
  periodo: { desde: "2026-06-01", hasta: "2026-06-30" },
  documentos: 146,
  totales_por_moneda: [mxn, usd],
  tendencia_mensual: [{ mes: "2026-06-01", totales_por_moneda: [mxn, usd] }],
  principales_proveedores: [
    { ...mxn, clave: "P1", nombre: "Proveedor de repuestos MXN" },
    { ...usd, clave: "P2", nombre: "Proveedor de refacciones USD" },
  ],
};
const semestre: ResumenComprasSae = {
  ...junio,
  periodo: { desde: "2026-01-01", hasta: "2026-06-30" },
  tendencia_mensual: ["01", "02", "03", "04", "05", "06"].map((mes, indice) => ({
    mes: `2026-${mes}-01`,
    totales_por_moneda: [{ ...mxn, importe: `${[114000, 82000, 136000, 97000, 122000, 183417][indice]}.35` }, usd],
  })),
};

async function ingresar(page: Page, isMobile: boolean) {
  await page.goto("/");
  await page.locator("#login-username").fill("admin");
  await page.locator("#login-password").fill("clave-de-prueba");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  if (isMobile) await page.getByRole("button", { name: "Mostrar barra lateral" }).click();
  return page.locator("#sidebar").getByRole("button", { name: "Aspel SAE", exact: true });
}

test("el periodo y la moneda se reflejan en los gráficos y en la pregunta de chat", async ({ page, isMobile }, info) => {
  let chatsCreados = 0;
  let envios = 0;
  const periodos: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "token-prueba", usuario } });
    if (url.pathname.endsWith("/auth/me")) return route.fulfill({ json: usuario });
    if (url.pathname.endsWith("/sae/resumen")) {
      periodos.push(url.search);
      return route.fulfill({ json: url.search ? junio : semestre });
    }
    if (url.pathname.endsWith("/chat/conversaciones/sae")) {
      chatsCreados += 1;
      return route.fulfill({ status: 201, json: { id: "sae-panel", tipo: "sae", titulo: "Chat de Aspel SAE", total_mensajes: 0 } });
    }
    if (url.pathname.endsWith("/chat/conversaciones/sae-panel")) return route.fulfill({ json: { mensajes: [] } });
    if (/\/chat(?:\/async)?$/.test(url.pathname)) envios += 1;
    return route.fulfill({ json: [] });
  });

  const panel = await ingresar(page, isMobile);
  await panel.click();
  await expect(page.getByRole("heading", { name: "Aspel SAE", exact: true })).toBeVisible();
  await expect(page.getByText("Compras registradas hasta el 1 de julio de 2026")).toBeVisible();
  await expect(page.getByLabel("Moneda")).toHaveValue("MXN");
  await expect(page.getByRole("region", { name: "Tendencia mensual" }).getByRole("button")).toHaveCount(6);
  await page.screenshot({ path: info.outputPath("panel-sae.png") });
  await page.getByRole("button", { name: /enero de 2026, .* MXN/ }).click();
  await expect(page.getByRole("button", { name: /enero de 2026, .* MXN/ })).toHaveAttribute("aria-pressed", "true");

  await page.getByLabel("Desde", { exact: true }).fill("2026-06-01");
  await page.getByRole("button", { name: "Aplicar periodo" }).click();
  await expect(page.getByRole("region", { name: "Tendencia mensual" }).getByRole("button")).toHaveCount(1);
  expect(periodos.at(-1)).toBe("?desde=2026-06-01&hasta=2026-06-30");
  await page.getByLabel("Moneda").selectOption("USD");
  await expect(page.getByTestId("sae-documentos")).toHaveText("146");
  await expect(page.getByTestId("sae-documentos-moneda")).toHaveText("5");
  await expect(page.getByTestId("sae-importe")).toHaveText("2,345.67");
  await expect(page.getByText("Proveedor de refacciones USD")).toBeVisible();
  await expect(page.getByText("Proveedor de repuestos MXN")).toHaveCount(0);

  await page.getByText("Ver datos mensuales", { exact: true }).click();
  await expect(page.getByRole("table").getByRole("cell", { name: "2,345.67" })).toBeVisible();
  await page.getByRole("button", { name: "Preguntar a Flucito" }).click();
  await expect(page.getByRole("textbox", { name: "Mensaje para Flucito" })).toHaveValue(/en USD.*2026-06-01 al 2026-06-30/);
  expect(chatsCreados).toBe(1);
  expect(envios).toBe(0);
});

test("distingue servicio no disponible, periodo vacío y falta de permiso", async ({ page, isMobile }) => {
  const cuenta = { ...usuario };
  let peticiones = 0;
  let disponible = false;
  await page.route("**/api/v1/**", async (route) => {
    const ruta = new URL(route.request().url()).pathname;
    if (ruta.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "token-prueba", usuario: cuenta } });
    if (ruta.endsWith("/auth/me")) return route.fulfill({ json: cuenta });
    if (ruta.endsWith("/sae/resumen")) {
      peticiones += 1;
      if (!disponible) return route.fulfill({ status: 503, json: { detail: { codigo: "sae_no_disponible", mensaje: "El respaldo de Aspel SAE no está disponible en este momento." } } });
      return route.fulfill({ json: { ...junio, documentos: 0, totales_por_moneda: [], tendencia_mensual: [], principales_proveedores: [] } });
    }
    return route.fulfill({ json: [] });
  });

  const panel = await ingresar(page, isMobile);
  await panel.click();
  await expect(page.getByRole("alert")).toContainText("El respaldo de Aspel SAE no está disponible");
  disponible = true;
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByTestId("sae-documentos")).toHaveText("0");
  await expect(page.getByText("No hay compras vigentes en el periodo seleccionado.")).toBeVisible();
  const peticionesConPermiso = peticiones;

  cuenta.acceso_sae = false;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByTestId("sae-documentos")).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveText("Para usar Aspel SAE, pide acceso a administración.");
  if (isMobile) await page.getByRole("button", { name: "Mostrar barra lateral" }).click();
  await expect(panel).toHaveAttribute("aria-disabled", "true");
  await panel.focus();
  await expect(page.locator("#sidebar").getByRole("tooltip")).toBeVisible();
  expect(peticiones).toBe(peticionesConPermiso);
});
