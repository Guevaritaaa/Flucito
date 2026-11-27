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

test("consulta facturas, devoluciones y existencias por almacén", async ({ page, isMobile }, info) => {
  const ventas = { moneda: "MXN", facturas: 30, importe_facturado: "14880.23", devoluciones: 2, importe_devoluciones: "561.72" };
  const lista = [{ clave: 1, nombre: "Principal" }, { clave: 2, nombre: "Secundario" }];
  const solicitudes: URLSearchParams[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const ruta = url.pathname;
    if (ruta.endsWith("/auth/login")) return route.fulfill({ json: { access_token: "token-prueba", usuario } });
    if (ruta.endsWith("/auth/me")) return route.fulfill({ json: usuario });
    if (ruta.endsWith("/sae/resumen")) return route.fulfill({ json: semestre });
    if (ruta.endsWith("/sae/facturacion")) return route.fulfill({ json: {
      corte, periodo: junio.periodo, facturas: 30, devoluciones: 2, totales_por_moneda: [ventas],
      tendencia_mensual: [{ mes: "2026-06-01", totales_por_moneda: [ventas] }],
    } });
    if (ruta.endsWith("/sae/inventario")) {
      solicitudes.push(url.searchParams);
      const almacen = lista.find((item) => String(item.clave) === url.searchParams.get("almacen")) ?? null;
      const pagina = Number(url.searchParams.get("pagina"));
      const existencias = [{ clave: pagina === 2 ? "SEGUNDO" : "PRIMERO", nombre: "Junta de prueba", unidad: "PZA", existencia: "1.500000", minimo: "3.000000" }];
      return route.fulfill({ json: {
        corte: { ...corte, ultimo_movimiento: "2026-07-01" }, almacen, almacenes: lista,
        articulos: almacen ? 18 : 40, sin_existencia: 3, bajo_minimo: 2,
        total_resultados: almacen ? 2 : 40, pagina, por_pagina: 1, existencias,
      } });
    }
    if (ruta.endsWith("/chat/conversaciones/sae")) return route.fulfill({ status: 201, json: {
      id: "sae-indicadores", tipo: "sae", titulo: "Chat de Aspel SAE", total_mensajes: 0,
    } });
    if (ruta.endsWith("/chat/conversaciones/sae-indicadores")) return route.fulfill({ json: { mensajes: [] } });
    return route.fulfill({ json: [] });
  });

  await (await ingresar(page, isMobile)).click();
  const modulos = page.getByRole("navigation", { name: "Módulos de Aspel SAE" });
  await modulos.getByRole("button", { name: "Facturación", exact: true }).click();
  await expect(page.getByText("Facturas registradas hasta el 1 de julio de 2026")).toBeVisible();
  const facturacion = page.getByRole("region", { name: "Facturación", exact: true });
  await expect(facturacion.getByText("14,880.23", { exact: true })).toBeVisible();
  await expect(facturacion.getByText("561.72", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Facturación mensual" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("facturacion.png") });

  await modulos.getByRole("button", { name: "Inventario", exact: true }).click();
  await expect(page.getByText("Último movimiento registrado el 1 de julio de 2026")).toBeVisible();
  await page.screenshot({ path: info.outputPath("inventario.png") });
  const filtros = page.getByRole("form", { name: "Filtros de inventario" });
  await filtros.getByLabel("Almacén").selectOption("2");
  await filtros.getByLabel("Artículo").fill("Junta");
  await filtros.getByLabel("Estado").selectOption("bajo_minimo");
  await filtros.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(page.getByRole("region", { name: "Existencias", exact: true })).toContainText("2 · Secundario");
  await expect(page.getByRole("cell", { name: "1.5", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Siguiente" }).click();
  await expect(page.getByText("SEGUNDO", { exact: true })).toBeVisible();
  expect(Object.fromEntries(solicitudes.at(-1)!)).toEqual({ almacen: "2", articulo: "Junta", estado: "bajo_minimo", pagina: "2" });

  await page.getByRole("button", { name: "Preguntar a Flucito" }).click();
  await expect(page.getByRole("textbox", { name: "Mensaje para Flucito" })).toHaveValue(/almacén 2.*bajo mínimo.*Junta/);
});
