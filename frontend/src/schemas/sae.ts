export interface PeriodoSae {
  desde: string;
  hasta: string;
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
  corte: {
    corte_id: string;
    empresa: string;
    fecha_respaldo: string | null;
    cobertura: PeriodoSae;
  };
  periodo: PeriodoSae;
  documentos: number;
  totales_por_moneda: TotalComprasMoneda[];
  tendencia_mensual: ComprasMes[];
  principales_proveedores: ComprasProveedor[];
}
