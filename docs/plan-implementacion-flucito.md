# Plan de implementación de Flucito

**Archivo:** `docs/plan-implementacion-flucito.md`.

**Estado:** fases 1 a 4 implementadas y validadas localmente. Fase 5 evaluada parcialmente y pospuesta por decisión del usuario: el servidor oficial de Google está en Developer Preview y la comparación no se completó. Sin commit, push ni despliegue. Luna 6 y Responses son los valores predeterminados; esfuerzo low y resumen opcional del modelo.

**Objetivo:** usar Luna como proveedor principal, hacer verificables las operaciones de Drive y mostrar en el chat el progreso real del agente. Cada fase se probará y revisará por separado. El primer despliegue conservará `gpt-5.6-luna` para poder medir el efecto del cambio de proveedor.

## Fase 1 · Usar Luna como principal y condicionar el respaldo de Groq

- Configurar `LLM_PRIMARY_PROVIDER=openai` en los valores predeterminados, el ejemplo de entorno y el despliegue. Registrar por llamada el proveedor, modelo, duración, resultado y motivo de respaldo, usando un ID de solicitud y omitiendo contenido y credenciales.
- Antes de recurrir a Groq, estimar la carga completa, incluidas las herramientas, y compararla con el presupuesto configurado. Usar inicialmente el límite de 8 000 TPM reportado para la cuenta. Un `413` descarta el reenvío de la misma carga. Retirar las llamadas auxiliares a Groq para redactar etiquetas de actividad.
- **Aceptación:** una consulta normal termina en Luna sin invocar Groq. Ante un fallo recuperable simulado de OpenAI, una consulta pequeña puede usar el respaldo y la del incidente, estimada en 11 273 tokens, lo omite y deja constancia del motivo.
- **Commit propuesto:** `feat: usar Luna como proveedor principal y limitar el respaldo de Groq`

## Fase 2 · Verificar operaciones de Drive y recuperar su resultado

- Empezar por «restablece la carpeta 17-11-2026». Resolver la carpeta por ID, comprobar su ubicación inicial y verificar el destino después de modificarla. Si existen varias coincidencias válidas, pedir al usuario que elija antes de mover nada.
- Guardar el avance de cada modificación antes de ejecutarla y actualizarlo al verificarla. Distinguir operación confirmada, parcial, fallida o pendiente de verificar. Tras una desconexión, consultar el estado en Drive antes de considerar otro intento.
- Si falla la redacción final o se alcanza el límite de rondas, construir la respuesta con los resultados guardados. El usuario debe saber qué cambió y qué sigue pendiente.
- **Aceptación:** interrumpir la respuesta después de restaurar una carpeta de prueba. Debe haber una sola modificación y la respuesta debe indicar el destino verificado. Repetir con desconexión durante la escritura, carpeta ambigua y acceso denegado.
- **Commit propuesto:** `fix: verificar operaciones de Drive y recuperar su resultado al cerrar el chat`

## Fase 3 · Integrar Responses API y comparar modelos

- Habilitar Responses API mediante una opción reversible, conservando LangGraph y FastAPI. Asociar cada resultado con su llamada a función, validar los argumentos en el backend y ejecutar en orden las escrituras dependientes.
- Reducir las herramientas enviadas en tareas de alcance claro, como consultar factores. Probar también peticiones mixtas para comprobar que el agente conserva acceso a las funciones necesarias.
- Comparar `gpt-5.6-luna` y `gpt-6-luna` con las mismas solicitudes de factores, reportes y carpetas. Mantener 5.6 como predeterminado hasta revisar exactitud, tareas completadas, latencia y costo por tarea resuelta.
- **Aceptación:** validar con la cuenta real una conversación directa, otra con varias herramientas y otra con adjuntos. Confirmar que el texto definitivo y el historial coinciden al terminar el streaming.
- **Commit propuesto:** `feat: integrar Responses API para las llamadas a funciones de Flucito`

## Fase 4 · Mostrar actividad comprensible en tiempo real

- Aprovechar el canal SSE y el sondeo existentes. En una restauración, mostrar «Buscando la carpeta», «Restaurando la carpeta» y «Verificando su ubicación» cuando empiece cada operación. Vincular el indicador final al resultado verificado.
- Mostrar los resúmenes de razonamiento que entregue el modelo bajo la etiqueta «Resumen del modelo». Si la cuenta o el modelo no los emiten, presentar las acciones observables. Conservar el desplegable cerrado inicialmente y guardar su contenido en el historial.
- **Aceptación:** desconectar el navegador a mitad de una operación y reconectar. Los pasos deben conservar su orden sin duplicarse. Probar también un error recuperado, un fallo definitivo, navegación por teclado, móvil e historial anterior.
- **Commit propuesto:** `feat: mostrar acciones verificables y resúmenes del modelo en el chat`

## Fase 5 · Evaluar MCP para consultar Drive

- Comparar el conector de solo lectura con la integración actual usando la misma identidad y los mismos permisos. Probar «¿qué carpetas hay?», «¿cuál es la última carpeta de reportes?» y una búsqueda por proveedor.
- Incluir carpetas anidadas, vacías e inaccesibles. Verificar que los resultados distinguen cada caso y que los botones de descarga corresponden únicamente a los archivos solicitados.
- **Criterio de adopción:** incorporar MCP si mejora la búsqueda o reduce el mantenimiento y conserva la precisión y los permisos en los casos probados. Mantener las escrituras en la ruta verificada de la fase 2.
- **Commit propuesto si se adopta:** `feat: incorporar búsquedas de Drive mediante MCP`

**Orden de entrega:** comenzar por la fase 1 y revisar el proveedor efectivo en los logs del servidor. Al cerrar cada fase se presentarán el diff, las pruebas ejecutadas, sus resultados y el mensaje de commit. El commit y el push quedarán sujetos a tu aprobación.

## Entrega de la fase 1

- `config.py`, `.env.example` y `docker-compose.yml`: OpenAI como principal, Luna 5.6 conservado, presupuesto de Groq de 8000 y reserva/salida máxima de 1024 tokens. También se corrigió el selector del `.env` local privado.
- `llm_router.py` y `graph.py`: estimación local del JSON completo de mensajes y herramientas antes de enviar a Groq. Si no cabe o no puede estimarse, no se envía y se propaga el error original. Un 413 no se reenvía. Los reintentos de los SDK se desactivan para que cada intento pase por el router.
- Logs JSON `llm_call`: ID compartido por invocación, proveedor, modelo, duración, resultado, motivo de respaldo, estimación y estado HTTP; sin contenido ni credenciales.
- `chat.py`: etiquetas públicas predefinidas, sin llamadas auxiliares a modelos.
- Pruebas de aceptación y regresión: `..\FlucitoEnv\Scripts\python.exe -m pytest tests -q --basetemp ..\pytest-temp-phase1-full`, desde `backend`: **117 aprobadas**. Se simularon fallos de proveedores; no se realizaron llamadas pagadas ni modificaciones en Drive. El caso de 11 273 tokens reproduce el tamaño reportado, no el contenido original del incidente.
- Límite conocido: la estimación es aproximada y el presupuesto se aplica por envío; no mide el consumo acumulado de todos los procesos o aplicaciones durante el minuto.
- Revisión pendiente en despliegue: confirmar `LLM_PRIMARY_PROVIDER=openai`, `OPENAI_MODEL=gpt-5.6-luna`, `GROQ_TPM_BUDGET=8000` y `GROQ_MAX_OUTPUT_TOKENS=1024`; enviar una consulta normal y comprobar `provider=openai`, `result=success` sin intento de Groq en los logs. Si hay variables existentes en Render, deben actualizarse allí.
- Commit propuesto: `feat: usar Luna como proveedor principal y limitar el respaldo de Groq`.
- Siguiente entrega: fase 2, detallada a continuación.

## Entrega de la fase 2

- Restaurar devuelve el contenido al estado sin procesar: conserva la misma carpeta de fecha en DOCUMENTOS ENTRADA/ANIO/MES/FECHA, extrae XML/PDF/TXT originales de los proveedores y envia a papelera reportes generales e individuales y carpetas verificadas vacias.
- Herramienta, esquema y prompt admiten una fecha o una lista con rutas_origen. Toda la seleccion se resuelve y prevalida antes de modificar; los homonimos requieren elegir ruta o ID. Nunca transforma una seleccion puntual en restauracion global.
- limpieza.py construye y guarda un plan por fecha antes de escribir. Los originales se mueven y verifican antes de retirar cualquier reporte. Solo se retiran los reportes reconocidos de Flucito (ENTRADAS_ALMACEN_*.xlsx y TXT COMAS/TABS). Archivos ajenos y documentos homonimos se conservan y requieren revision.
- operaciones_drive.py guarda movimientos, papelera y resultado agregado. Escrituras sin reintentos; lecturas independientes para verificar. Una respuesta perdida no provoca otro envio. El chat y el limite de rondas usan el diario, incluso si falla la redaccion final, y guardan el resultado en el historial.
- Tras verificar la restauracion se liberan solo los IDs de los originales seleccionados del estado incremental. No se eliminan factores, configuracion ni todas las bases o JSON locales.
- La restauracion global de pruebas delega el mismo flujo a todas las fechas, sin crear ENTRADAS AL INVENTARIO ni mover fechas fuera de DOCUMENTOS ENTRADA.
- Correccion de rutas antiguas: queda inactiva la reubicacion por falta de reporte hacia la bandeja antigua; auditoria y revision consideran valida una fecha pendiente en DOCUMENTOS ENTRADA; ordenar conserva la jerarquia actual, incluidas fechas vacias; crear una fecha por nombre corto usa DOCUMENTOS ENTRADA/ANIO/MES. Se mantiene lectura de cargas antiguas y migracion explicita de carpetas procesadas hacia la estructura actual.
- Dockerfile mantiene un worker: la exclusion de escrituras simultaneas es por proceso. Conservar PostgreSQL o el volumen SQLite entre reinicios. Varias replicas requieren bloqueo distribuido.
- Evidencia local del incidente: la copia del 17 contiene dos carpetas de proveedor, dos XML y seis reportes individuales, sin reportes generales en la raiz. Una prueba lee solo nombres y estructura de C:/Users/rober/Proyectos/Docs para simular Drive; comprueba dos XML directos, seis reportes y dos subcarpetas en papelera. No modifica la copia ni Drive real.
- Pruebas finales desde backend: `..\FlucitoEnv\Scripts\python.exe -m pytest tests -q --basetemp ..\pytest-temp\restauracion-validada`. **140 pruebas aprobadas**. Incluye el caso local del 17 usando Drive simulado y el cierre del chat tras un fallo de redaccion.
- Pendiente de despliegue: validar con una carpeta aislada de Drive real, comprobar contenido, papelera e historial tras una interrupcion. No se ejecutaron operaciones contra Drive real ni se modifico la copia local Docs.
- Las carpetas temporales de la fase 1 permanecen porque la politica de ejecucion bloqueo su borrado. Las pruebas posteriores usan pytest-temp, ya excluida de Git.
- Commit propuesto: `fix: restablecer carpetas sin procesar dentro de Documentos Entrada`.
- Siguiente entrega: fase 3, detallada a continuación.

## Entrega de la fase 3

- `llm_router.py`, configuración, `.env.example` y Docker Compose: `OPENAI_USE_RESPONSES_API` permite cambiar entre Responses y Chat Completions. Se conservan FastAPI, LangGraph y `gpt-5.6-luna`. Responses queda desactivado por defecto hasta validar la cuenta real. Contexto explícito, `store=false`, sin `previous_response_id` ni reintentos ocultos.
- `ejecucion_tools.py`: validación Pydantic de todo el lote antes de ejecutar; tipos estrictos, campos extra prohibidos, funciones conocidas e IDs únicos. Ejecución secuencial con el ID original en cada resultado. Fallo, cancelación o confirmación detienen las llamadas restantes; las no ejecutadas reciben resultado explícito. Se desactiva `parallel_tool_calls` de OpenAI.
- `seleccion_tools.py` y grafo: preguntas inequívocas de factores reciben solo `consultar_almacen`; las mixtas y ambiguas conservan todas las herramientas. La misma selección se valida antes de ejecutar. `LLM_REDUCE_TOOLS_ENABLED=false` revierte la reducción.
- Los bloques Responses y sus argumentos se conservan de forma coherente con las llamadas ejecutadas. Al pasar a Groq o Chat Completions se normaliza una copia del mensaje, sin alterar el historial. Los logs incorporan el transporte efectivo en `api`.
- `chat.py`: el texto definitivo normalizado, el evento SSE final y el historial coinciden al completar el job; se conservan los enlaces de reportes. Los argumentos y bloques de razonamiento no se mezclan con el texto final. Los adjuntos verificados son enlaces del flujo actual; los XML/PDF/TXT siguen entrando por `/almacen/upload`, sin añadir archivos binarios a ChatRequest.
- Se corrigió un desajuste previo entre prompt y esquema: `generar_entradas_almacen` ahora admite `carpeta_especifica` y la sincronización filtra esa única fecha/ID antes de procesar. Si falta o es ambigua, no procesa otras fechas. La selección se conserva entre confirmaciones. También se corrigió el literal de la acción de archivado que anunciaba el prompt.
- `evaluations/comparar_responses.py` y `casos_responses.json`: protocolo reproducible para ambos modelos, con herramientas y datos aislados; nunca modifica Drive real. Mide llamadas correctas, criterios automáticos de respuesta, tareas resueltas, tokens y latencia. El costo requiere tarifas explícitas y uso verificable; en otro caso queda en null. La revisión humana de exactitud sigue siendo necesaria.
- Comprobación de cuenta real: la clave efectiva procede del `.env` local y OpenAI respondió HTTP 401 al consultar modelos. No hay credenciales Drive locales. El intento no generó respuestas ni resultados de comparación; la evidencia sin secretos está en `docs/evaluaciones/responses-cuenta-local.json`. El protocolo actualizado, sin métricas inventadas, está en `docs/evaluaciones/responses-protocolo.json`.
- Pruebas: SDK real con transporte HTTP simulado para comprobar `/v1/responses`, esquemas, call_id, streaming dentro de LangGraph, lotes secuenciales, validación, peticiones mixtas, enlaces de reporte, alcance por fecha y cierre SSE/historial. Desde `backend`: `..\FlucitoEnv\Scripts\python.exe -m pytest tests -q --basetemp ..\pytest-temp\fase3-regresion`: **166 aprobadas**. `git diff --check` sin errores.
- Para cerrar aceptación: configurar una clave OpenAI válida y credenciales Drive fuera de Git; confirmar acceso a ambos modelos; activar Responses en un entorno de prueba; validar conversación directa, varias herramientas y enlaces de reporte con la cuenta real. Ejecutar la comparación y revisar exactitud, finalización, latencia y costo antes de considerar un cambio de modelo. No se inició la fase 4.
- Commit propuesto: `feat: integrar Responses API para las llamadas a funciones de Flucito`.

### Validación real del 22-11-2026

El bloqueo anterior de credenciales quedó resuelto. La cuenta muestra ambos modelos;
OAuth lee la raíz Docs y Groq devuelve una respuesta. No se ejecutaron herramientas
de escritura contra Drive. Los resultados de restauración/generación de la comparación
provienen de herramientas aisladas, con modelos reales.

El chat completo se probó con Responses activada solo en el proceso de validación,
Luna 6 (modelo elegido en el .env del usuario), LangGraph, callbacks, SQL e intercambio SSE. Pasaron conversación directa,
consulta de factores y consulta conjunta de factores más reportes del 14-11-2026.
En las tres coinciden respuesta, provisional final, SSE e historial. La última ejecutó
consultar_almacen y consultar_drive; devolvió dos adjuntos cuya existencia y acceso
se comprobaron por ID. Evidencia: `docs/evaluaciones/responses-integracion-real.json`.

Comparación: `docs/evaluaciones/responses-cuenta-validada.json`. Una ejecución por
caso y modelo, cinco casos iguales, herramientas aisladas y Responses API:

| Modelo | Casos completados | Mediana de latencia | Costo estimado por caso resuelto (USD) |
| --- | --- | --- | --- |
| gpt-5.6-luna | 5/5 | 2856.48 ms | 0.000607588 |
| gpt-6-luna | 5/5 | 3282.44 ms | 0.000277534 |

Costos calculados sobre tokens medidos y [tarifas Standard de contexto corto](https://developers.openai.com/api/docs/pricing.md)
consultadas el 22-11-2026, guardadas en `docs/evaluaciones/precios-standard-2026-11-22.json`.
Son estimaciones, no factura; excluyen impuestos, recargos regionales y escrituras de
caché no desglosadas. La coincidencia de herramientas y texto se evaluó automáticamente;
la muestra es pequeña, con caché y sin aleatorizar el orden. El predeterminado del repositorio se mantiene en gpt-5.6-luna, sin alterar la selecci?n local del usuario de gpt-6-luna,
y no se generalizan estos cinco resultados a todas las tareas reales de negocio.

Para repetir: desde backend, `..\FlucitoEnv\Scripts\python.exe -m evaluations.comparar_responses --live --precios ..\docs\evaluaciones\precios-standard-2026-11-22.json`.
Las conversaciones de prueba quedaron guardadas con IDs de sesión `validacion-responses-*`.

Se añadió `tests/conftest.py` para aislar las credenciales y el modelo de la regresión.
Al configurar el usuario Luna 6 en su .env, tres pruebas que esperaban Luna 5.6 fallaban;
ahora el entorno de pruebas fija su propio modelo sin cambiar el .env del usuario.

## Entrega de la fase 4

- `actividad.py`, `limpieza.py` y `ActividadHandler`: eventos observables «Buscando la carpeta», «Restaurando la carpeta» y «Verificando su ubicación». Cada paso se actualiza por ID estable. Solo la comprobación final marca éxito; los fallos y resultados parciales conservan su estado.
- Configuración, ejemplo de entorno y Compose: Luna 6 y Responses como predeterminados, esfuerzo `low` y solicitud de resumen `auto`. El `.env` local activa esas opciones sin tocar credenciales. Chat Completions sigue disponible con razonamiento none. Reiniciar el backend para recoger la configuración.
- Los resúmenes públicos entregados por Responses se actualizan durante el streaming y se consolidan al terminar. Se guardan en actividades e historial bajo «Resumen del modelo». No se muestra razonamiento cifrado ni una narración inventada. Si no hay resumen, se muestran las acciones observables.
- `ActividadDesplegable.tsx`: cerrado inicialmente, etiquetas comprensibles, estados accesibles, teclado, modo oscuro, adaptación móvil y compatibilidad con historial anterior sin actividad o sin resumen.
- `chatService.ts` y `useChat.ts`: SSE y sondeo consultan el mismo job. Su ID pendiente se conserva en sessionStorage para reanudar tras recargar o reconectar sin otro POST de ejecución. Los snapshots reemplazan el estado y mantienen IDs y orden. La reanudación es en la misma pestaña y depende de que el job siga disponible; no agrega recuperación tras reiniciar el servidor.
- Validación: **172 pruebas backend aprobadas**, **8 pruebas Playwright** en escritorio y móvil, build de producción correcto. Incluye conexión interrumpida, sondeo, recarga, un solo POST, pasos sin duplicados, error definitivo, recuperación, parcial, teclado e historial antiguo. Se inspeccionaron capturas desktop/móvil. Detector Impeccable sin hallazgos.
- Cuenta real: `docs/evaluaciones/fase4-cuenta-real.json`: Luna 6, Responses y esfuerzo low completaron una consulta de factores y guardaron la actividad. El proveedor no emitió resumen en esa consulta sencilla; se conservó la alternativa de acciones. Las pruebas del canal cubren resúmenes entregados y exclusión del contenido cifrado. Las restauraciones de esta fase usaron Drive simulado.
- Se incorpora la elección del usuario de Luna 6. La [ficha oficial](https://developers.openai.com/api/docs/models/gpt-6-luna.md) confirma la restricción de Chat Completions con funciones y reasoning none. Los porcentajes de alucinación o un ahorro fijo del 62% no se adoptan como garantías de Flucito: el costo por tarea depende del uso y los tokens medidos.
- Commit propuesto: `feat: mostrar acciones verificables y resúmenes del modelo en el chat`.
- Siguiente entrega: fase 5, evaluación de MCP para consultas de Drive. No iniciada.
Regresión final con el entorno aislado: `..\FlucitoEnv\Scripts\python.exe -m pytest tests -q --basetemp ..\pytest-temp\fase3-entorno-aislado`: **166 aprobadas**. `git diff --check` sin errores.
