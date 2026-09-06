# Historial de cambios

Este archivo resume cambios importantes de Flucito. Los commits contienen el detalle técnico de cada modificación.

## [0.1.0] - 2026-09-05

Primera versión funcional del asistente.

### Agregado

- Backend construido con FastAPI y LangGraph.
- Chat con memoria temporal por `session_id`.
- Herramienta `generar_entradas_almacen` integrada al grafo del agente.
- Groq como proveedor principal de lenguaje.
- OpenAI como fallback ante errores recuperables de Groq.
- Endpoint ligero `/health` para monitoreo.
- Carga de XML, PDF y TXT desde el frontend.
- Agrupación de documentos relacionados con facturas.
- Integración con Google Drive mediante OAuth y cuenta de servicio.
- Extracción de datos fiscales y conceptos desde XML CFDI.
- Uso de PDF/TXT como apoyo para validar o completar información.
- Generación de Excel acumulativo de entradas de almacén.
- Resumen JSON del procesamiento.
- Estado de sincronización para evitar documentos duplicados.
- Pruebas automatizadas para API, chat, fallback, documentos, almacén y Drive.
- Documentación inicial de arquitectura, configuración, uso, pruebas y herramientas.

### Limitaciones conocidas

- La memoria conversacional se pierde cuando se reinicia el proceso.
- El Excel y el estado local viven en almacenamiento temporal de Render.
- La generación del reporte ocurre dentro de la solicitud.
- La extracción todavía requiere revisión humana.
- No se generan facturas fiscales automáticamente.
- No se modifica directamente Aspel SAE.
- No existe todavía un modelo de machine learning para inventario.

## Próximamente

- Persistencia de conversaciones en base de datos.
- Manejo de errores más detallado para integraciones externas.
- Mayor cobertura de pruebas de integración.
- Interfaz de usuario completa.
- Consultas de inventario y reportes comerciales.
- Automatización gradual de facturación y procesos de almacén.
- Análisis de productos con baja rotación y prevención de falta de stock.
