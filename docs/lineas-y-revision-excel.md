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

## Fase 2: sugerencias confirmadas

Se agrupan hasta tres referencias por línea, exigiendo familia de código, secuencia de medidas, clave SAT y unidad SAT iguales. Las diferencias de sufijo/modelo se muestran mediante la clave y descripción completas. No se equiparan fracciones con enteros. Sin referencia fiable se ofrece completar el Excel. La elección registra referencia y confirmación; una referencia que cambió se rechaza. La línea vacía bloquea ambos TXT y deja únicamente los cinco precios de venta vacíos, conservando compra.

Validación: 32 pruebas aprobadas de decisiones, catálogo y líneas. Se consultó el esquema de la copia reciente de Firebird en transacción de solo lectura: `INVE02.LIN_PROD` y `CLIN02.CVE_LIN` tienen longitud 5. Los códigos manuales se validarán con ese límite.

## Fase 3: Excel corregido y factores

Solo las filas originalmente pendientes admiten cambio de línea. Se normalizan espacios exteriores y mayúsculas; los códigos admitidos son de 1 a 5 caracteres ASCII alfanuméricos, guion y guion bajo. No se exige que existan en la copia del catálogo ni se expanden por parecido a otra línea. Se conserva compra; los precios manuales positivos y finitos se respetan y únicamente los vacíos se calculan.

Sin factor, se guarda una nueva versión del Excel recibido y se abre la tarjeta de factores existente. La confirmación reanuda esa copia persistida; elegir precios manuales conserva los pendientes y permite descargar esa versión para terminarla. Una versión anterior o una confirmación repetida se rechazan. Las preferencias de factor se consultan por código exacto y únicamente se guardan con la casilla expresa del usuario. La línea confirmada no crea altas en SAE.

Validación de esta fase: 30 pruebas aprobadas, incluidas líneas YPC con cero, dos o cinco precios manuales; líneas DAYCO sin factor y ZZ9 ausente del catálogo; reanudación; precios manuales y rechazo de formatos incompatibles.

## Fase 4: estado visible y continuidad

Se aplicó la guía local `emil-design-eng`: avisos ámbar con icono, título, explicación y acción; contraste en claro y oscuro; controles nativos por teclado y foco visible. Los errores bloqueantes conservan rojo. No se añadieron animaciones a estas decisiones frecuentes. Los avisos estructurados viajan en la respuesta y se guardan en el historial.

| Antes | Después |
| --- | --- |
| Línea ausente dentro del texto general | Aviso ámbar con fuentes y acción explícita |
| Subida centrada solo en precios | Revisión de líneas, precios manuales y factor |
| Excel subido sin estado intermedio visible | Versión guardada y tarjeta de factor recuperable al recargar |
| Tarjetas repetidas al continuar | Solo la tarjeta vigente de cada reporte; texto histórico conservado |

La confirmación de un factor de revisión continúa sin llamar al modelo ni reprocesar los documentos. El chat y su memoria registran el nombre del reporte, la línea, el factor y los precios completados o conservados. Las descargas de ambos TXT permanecen bloqueadas durante los pendientes.
