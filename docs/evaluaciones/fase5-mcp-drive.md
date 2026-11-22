# Evaluación de MCP para Drive

Estado: evaluación parcial cerrada como pospuesta por decisión del usuario. No se adoptó MCP porque el servidor oficial está en Developer Preview y la comparación de precisión y permisos no pudo completarse. Se conserva la integración actual de Google Drive.

Actualización después de habilitar la API: `initialize` responde HTTP 200 y la
llamada `search_files` llega al servidor (HTTP 200 de transporte), pero el resultado
MCP contiene `isError=true` y el mensaje «The caller does not have permission».
La lectura de la raíz mediante Drive API tradicional sigue funcionando con las
mismas credenciales OAuth; el token indica alcance Drive y tiene refresh token.
El mensaje MCP no identifica si la causa es propagación, el cliente marcado para
agente, el programa Developer Preview u otra política. No se ha adoptado MCP.
La captura muestra la casilla marcada y el botón Guardar; no confirma que se haya
guardado o propagado. Google indica que el servidor requiere Developer Preview.

Tras la confirmación del usuario de que guardó el cambio, se volvió a probar con
un token renovado. Google valida el token y confirma el alcance `drive`; el cliente
del token coincide con la credencial configurada. Tanto una búsqueda por texto
como una búsqueda sin texto devolvieron el mismo error MCP de permiso. La Drive API
tradicional sigue leyendo la raíz correctamente. Google documenta que la membresía
en Developer Preview y el registro del proyecto son requisitos y que pueden tardar
unos días: https://developers.google.com/workspace/preview . No se ha demostrado que
esa sea la causa en esta cuenta; también puede estar pendiente la propagación.

El usuario eligió el servidor oficial de Google `https://drivemcp.googleapis.com/mcp/v1`.
El 22-11-2026 se probó con el token OAuth existente: `initialize` respondió HTTP 200;
`search_files` devolvió HTTP 403 porque Drive MCP API está deshabilitada en el proyecto
de ese token. El diagnóstico usa `python -m evaluations.verificar_mcp_google` desde
backend y solo permite `search_files` y `get_file`; no habilita funciones de escritura.
Después de activar la API, comprobar nuevamente y revisar Developer Preview y la
opción OAuth «Use this client for an AI-powered agent». No se han cambiado permisos.

La integración actual usa Google Drive API con las credenciales OAuth configuradas
en Flucito. No hay un servidor MCP de Google Drive configurado en el proyecto ni
un conector de Google Drive disponible entre las herramientas de esta sesión.
Por tanto, todavía no se puede comparar con la misma identidad y permisos.

Se inició una lectura de `explorar_estructura_drive(ubicacion="todas",
incluir_archivos=False)` con la cuenta configurada. Tras más de 30 segundos sin
resultado se interrumpió: este dato indica una posible latencia, pero no permite
concluir que la consulta haya fallado ni establecer una medición completa. Las
consultas de reportes y proveedor de ese mismo intento no llegaron a ejecutarse.
No se escribieron archivos en Drive.

Para completar la evaluación se necesita identificar y configurar un servidor MCP
de Drive de solo lectura, verificar que use exactamente la identidad OAuth y el
alcance de carpetas de la integración actual y ejecutar ambas rutas con los mismos
casos: listado general, último reporte, proveedor, carpetas anidadas/vacías,
carpetas inaccesibles y correspondencia de enlaces de descarga. Registrar tiempos,
errores, resultados y mantenimiento; no adoptar MCP hasta superar el criterio del
plan. Las escrituras permanecen en la ruta verificada de la fase 2.
