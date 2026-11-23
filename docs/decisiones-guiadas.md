# Contrato de decisiones guiadas

El chat síncrono, el asíncrono y el historial admiten `interaccion` y `revision_reporte`
opcionales. Los mensajes antiguos siguen funcionando sin estos campos.

`interaccion` incluye `id`, `revision`, `estado`, `preguntas`, `respuestas`,
`permite_recordar` y, cuando corresponde, `anteriores`. Cada pregunta contiene opciones
con identificador, título y descripción. El cliente devuelve identificadores, no
instrucciones para reinterpretar con el modelo.

## Guardado y confirmación

- `PUT /api/v1/chat/conversaciones/{session_id}/decisiones`: guarda un borrador.
- `POST /api/v1/chat` o `POST /api/v1/chat/async`: confirma o cancela mediante el campo
  `decisiones`. La confirmación asíncrona reutiliza el SSE/polling y la recuperación de jobs.

El envío de decisiones contiene `interaccion_id`, `revision`, `accion`
(`borrador`, `confirmar` o `cancelar`) y un mapa `respuestas`. Cada respuesta incluye
`opcion`, `recordar` y `campos`. El borrador también valida opciones e identidad; permite
formularios incompletos. Confirmar valida todas las preguntas y el factor personalizado.

Los campos de un factor personalizado son `nombre` y `precios`. Cada uno de los cinco
precios contiene `base` (`COSTEO` o `PUBLICO`) y `pasos`, con `operacion` (`*` o `/`)
y `valor` positivo. Público solo admite COSTEO como base. El servidor construye y evalúa
las expresiones con un intérprete aritmético limitado, sin `eval`.

El backend utiliza comparación y actualización atómicas del documento persistido para
reservar la ejecución. Una revisión obsoleta o una confirmación repetida devuelve 409.
Una ejecución interrumpida no se repite automáticamente. Las herramientas vuelven a
resolver los destinos de Drive; si cambió el contenido de una carpeta cuya eliminación
se autorizó, se devuelve otra pregunta antes de enviar nada a la papelera.

`ConfirmacionPendiente` conserva el estado de cada conversación. `preferencias_decision`
separa las preferencias por usuario y contexto, sin escribir factores globales. Aplicar
la migración Alembic `0002_preferencias_decision` en instalaciones gestionadas mediante
migraciones. La inicialización habitual también registra el nuevo modelo.

## Validación del Excel corregido

- `GET /api/v1/almacen/reportes/{id}?session_id=...`: estado de la versión.
- `GET /api/v1/almacen/reportes/{id}/archivo?session_id=...&formato=xlsx|comas|tabs`: descarga.
- `POST /api/v1/almacen/reportes/{id}/validar?session_id=...`: multipart con `archivo` `.xlsx`.

Los endpoints comprueban usuario y conversación. El libro contiene identificadores de
versión y filas ocultos; el manifiesto original permanece en el servidor. Se permiten
correcciones numéricas de precios, no cambios de productos u otros datos. Las fórmulas
originales sin cambios se recalculan con aritmética limitada y referencias a precios
de su misma fila; las fórmulas nuevas, macros y vínculos externos se rechazan. No se
confía en los valores calculados almacenados por el archivo subido.

Una validación fallida devuelve 422 con `detail.errores`, una lista de `producto`, `campo`
y `motivo`. Conserva el original y bloquea el TXT. Las validaciones simultáneas usan un
archivo de exclusión por reporte, además de la exclusión entre hilos. Un bloqueo que
persista tras una caída requiere comprobar el resultado de Drive antes de retirarlo.

Los manifiestos y copias están en `.revisiones` dentro de la carpeta de datos. Debe
montarse un volumen persistente compartido si hay varias instancias. Las pruebas de
Drive usan clientes simulados: no requieren ni modifican documentos de producción.
