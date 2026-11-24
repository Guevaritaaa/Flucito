# Líneas pendientes y revisión del Excel

## Alcance acordado

Entrega local para revisión de los asesores. No incluye moneda ni consulta a SAE en producción. Se admiten códigos de línea escritos por el asesor aunque no existan en la copia disponible. Las sugerencias necesitan confirmación; recordar un factor requiere elección expresa.

## Fase 1: fuentes y explicaciones

Cada producto conserva clave de apoyo, clave XML, coincidencia en el catálogo del SAE y procedencia de línea. Se distingue apoyo ausente, lectura fallida, partida no emparejada y columna de línea vacía. La explicación se conserva en los comentarios de clave y línea del Excel y en el resumen del reporte. Las inferencias de una línea única dentro del apoyo conservan el valor original vacío.

Validación inicial: 16 pruebas aprobadas (procedencia general, `BW-SAF4000DME`, otra clave sintética, apoyo ilegible, resumen del chat y pipeline).

## Fases siguientes

2. Sugerencias conservadoras por familia de código, SAT y unidad; decisión por producto y trazabilidad de referencia.
3. Corrección de líneas pendientes y precios en Excel, con persistencia de la versión revisada mientras se elige factor.
4. Avisos ámbar accesibles, resumen de decisiones, continuidad en el chat y descargas verificadas.
5. Regresiones, revisión visual y reproceso aislado de las 44 carpetas locales. Resultados y capturas se documentarán aquí.
