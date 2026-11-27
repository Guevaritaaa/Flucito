const fechaLarga = new Intl.DateTimeFormat("es-MX", { dateStyle: "long", timeZone: "UTC" });
const mesLargo = new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric", timeZone: "UTC" });
const mesCorto = new Intl.DateTimeFormat("es-MX", { month: "short", timeZone: "UTC" });
const importes = new Intl.NumberFormat("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const conteoSae = new Intl.NumberFormat("es-MX");

export const fechaSae = (iso: string) => fechaLarga.format(new Date(iso));
export const mesSae = (iso: string) => mesLargo.format(new Date(iso));
export const etiquetaMesSae = (iso: string) => mesCorto.format(new Date(iso)).replace(/\.$/, "");

export function importeSae(decimal: string): string {
  const [entero, fraccion = ""] = decimal.split(".");
  // La API envía decimales como texto. Conserva los centavos al formatear importes grandes.
  const valor = entero === "-0" ? -0 : BigInt(entero);
  return importes.formatToParts(valor)
    .map((parte) => parte.type === "fraction" ? fraccion.padEnd(2, "0").slice(0, 2) : parte.value)
    .join("");
}
