export interface PeriodoSae {
  desde: string;
  hasta: string;
}

interface CorteSae {
  corte_id: string;
  empresa: string;
  fecha_respaldo: string | null;
}

export interface TotalComprasMoneda {
  moneda: string;
  documentos: number;
  importe: string;
}

export interface ComprasMes {
  mes: string;
  totales_por_moneda: TotalComprasMoneda[];
}

export interface ComprasProveedor extends TotalComprasMoneda {
  clave: string | null;
  nombre: string | null;
}

export interface ResumenComprasSae {
  corte: CorteSae & { cobertura: PeriodoSae };
  periodo: PeriodoSae;
  documentos: number;
  totales_por_moneda: TotalComprasMoneda[];
  tendencia_mensual: ComprasMes[];
  principales_proveedores: ComprasProveedor[];
}

export interface FacturacionMoneda {
  moneda: string;
  facturas: number;
  importe_facturado: string;
  devoluciones: number;
  importe_devoluciones: string;
}

export interface ResumenFacturacionSae {
  corte: CorteSae & { cobertura: PeriodoSae };
  periodo: PeriodoSae;
  facturas: number;
  devoluciones: number;
  totales_por_moneda: FacturacionMoneda[];
  tendencia_mensual: { mes: string; totales_por_moneda: FacturacionMoneda[] }[];
}

export type EstadoInventarioSae = "todos" | "sin_existencia" | "bajo_minimo";

export interface FiltroInventarioSae {
  almacen: string;
  articulo: string;
  estado: EstadoInventarioSae;
  pagina: number;
}

interface AlmacenSae {
  clave: number;
  nombre: string;
}

export interface ResumenInventarioSae {
  corte: CorteSae & { ultimo_movimiento: string | null };
  almacen: AlmacenSae | null;
  almacenes: AlmacenSae[];
  articulos: number;
  sin_existencia: number;
  bajo_minimo: number;
  total_resultados: number;
  pagina: number;
  por_pagina: number;
  existencias: { clave: string; nombre: string | null; unidad: string | null; existencia: string | null; minimo: string | null }[];
}
