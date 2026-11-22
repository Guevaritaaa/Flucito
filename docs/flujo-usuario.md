# Flujo de uso de Flucito

Esta guía describe el recorrido normal para procesar documentos de facturas y actualizar la base de entradas de almacén.

## Qué necesitas antes de empezar

Para cada factura, reúne los documentos disponibles:

- XML del CFDI: fuente principal de datos.
- PDF de la factura: apoyo visual y validación.
- TXT: alternativa cuando no existe PDF.

No es obligatorio tener los tres archivos. El XML sí, es el documento principal. PDF y TXT ayudan a completar o revisar información.

## 1. Abrir Flucito

Abre la dirección del frontend desplegado o ejecuta la interfaz local. Espera a que aparezca el cuadro de conversación.

Si la pantalla no carga o el asistente no responde, revisa primero:

```text
https://tu-dominio.onrender.com/health
```

Una respuesta `{"status":"ok"}` indica que el backend está activo.

## 2. Seleccionar documentos

Pulsa **Adjuntar documentos** y selecciona XML, PDF o TXT.

Recomendaciones:

- Selecciona todos los archivos relacionados con una misma factura.
- Conserva los nombres originales cuando sea posible.
- No subas archivos que no correspondan a facturas.
- Respeta el límite actual de 150 archivos por carga.
- Cada archivo puede pesar hasta 20 MB.

El backend agrupa archivos usando la información disponible en su nombre y contenido. Si dos documentos pertenecen a la misma factura, conviene que compartan un identificador o folio reconocible.

## 3. Subir archivos a Google Drive

Pulsa el botón para cargar los documentos. Flucito los guarda en `docs/DOCUMENTOS ENTRADA/AÑO/MES/DD-MM-AAAA`. Al subir desde la interfaz, usa la fecha actual para nombrar la carpeta de carga. Si el asesor carga documentos directamente en Drive, debe colocarlos en esa misma jerarquía.

La interfaz debe mostrar una confirmación cuando la carga termina. Si aparece un error:

- revisa que la sesión de Google siga autorizada;
- confirma que la carpeta raíz exista;
- confirma que la cuenta autenticada tenga permiso para subir archivos;
- revisa los logs de Render si el problema continúa.

La carga a Drive y la generación del reporte son pasos distintos. Subir los archivos no actualiza necesariamente el Excel en ese instante. Los archivos colocados directamente en la raíz `docs` o en otra carpeta no se procesan como cargas nuevas.

## 4. Pedir el reporte

Después de cargar los archivos, escribe un mensaje claro en el chat. Ejemplos:

```text
Genera el reporte de entradas de almacén.
```

```text
Procesa las facturas nuevas y actualiza el Excel.
```

```text
Dame el último reporte de entradas de almacén.
```

El agente reconoce la intención y puede invocar la herramienta `generar_entradas_almacen`. Esa herramienta sincroniza documentos nuevos desde Drive, extrae los datos y actualiza el libro acumulativo.

## 5. Qué procesa Flucito

Durante el procesamiento, Flucito revisa las fechas de `docs/DOCUMENTOS ENTRADA/AÑO/MES`. Los reportes se generan en esa misma fecha:

```text
docs/
└── DOCUMENTOS ENTRADA/{AÑO}/{MES}/{fecha de carga}/
    ├── {proveedor} - {fecha}/                      # originales y reportes individuales
    ├── ENTRADAS_ALMACEN_{fecha}.xlsx               # reporte general de la fecha
    ├── ENTRADAS_ALMACEN_{fecha}_COMAS.txt
    └── ENTRADAS_ALMACEN_{fecha}_TABS.txt
```

La fecha de la carpeta de entrada se conserva en el archivo. El nombre de la subcarpeta del proveedor se obtiene del XML; dentro se agrupan la factura, sus documentos de apoyo y su Excel individual.

Durante el procesamiento:

1. Busca fechas y documentos nuevos dentro de `DOCUMENTOS ENTRADA/AÑO/MES`.
2. Ignora documentos que ya aparecen como procesados.
3. Lee los datos fiscales del XML.
4. Extrae conceptos, cantidades, precios y códigos disponibles.
5. Usa PDF o TXT como apoyo cuando el XML no contiene algún dato esperado.
6. Registra errores o inconsistencias en la hoja correspondiente.
7. Agrega únicamente documentos nuevos al Excel acumulativo.
8. Genera un resumen para la respuesta del asistente.

Si una factura ya fue procesada, el estado de Drive ayuda a evitar duplicarla en el reporte.

### Restablecer una o varias fechas

«Restablece la carpeta 17-11-2026» devuelve esa fecha al estado sin procesar:
extrae los XML, PDF y TXT originales de las subcarpetas de proveedor, los deja directamente
en la carpeta de fecha y envía a papelera los reportes generados (Excel y TXT COMAS/TABS),
tanto individuales como generales. Retira las subcarpetas únicamente después de verificar
que están vacías. Conserva el ID, nombre y ubicación de la fecha y libera solo los originales
seleccionados del estado incremental para permitir reprocesarlos. No borra factores ni configuración.

Se pueden indicar varias fechas en la misma solicitud. Se validan todas antes de escribir.
Si hay fechas homónimas, Flucito pide elegir por ruta completa o ID. Una interrupción informa
los pasos confirmados y los pendientes; al repetir la solicitud se consulta el estado actual.
Archivos no reconocidos o documentos homónimos se conservan y requieren revisión, sin borrado automático.

## 6. Descargar el Excel

Cuando el reporte termina, el asistente muestra un enlace de descarga. También puede descargarse mediante:

```text
GET /api/v1/almacen/download
```

El archivo contiene la base acumulativa y sus hojas de trabajo. Antes de importarlo a otro sistema, revisa la hoja de errores y confirma que los conceptos principales estén completos.

## 7. Si aparecen errores

### El asistente responde que ocurrió un error

Revisa los logs del backend. Puede tratarse de un proveedor LLM temporalmente no disponible, una credencial inválida o un problema de Google Drive.

### Se suben los archivos, pero no se genera el reporte

Confirma que después de cargar los archivos enviaste un mensaje solicitando explícitamente el reporte. La carga y el procesamiento no son la misma operación.

### Aparecen errores en el Excel

Abre la hoja **Errores**. El XML puede estar incompleto, usar un formato no contemplado o no coincidir con su PDF/TXT de apoyo.

### El reporte no incluye archivos recientes

Comprueba que los archivos estén dentro de la carpeta de Drive configurada y que la cuenta autenticada tenga permiso para leerla. Después vuelve a solicitar el reporte.

### El enlace de descarga no funciona después de reiniciar Render

La base generada vive en el almacenamiento temporal del servicio. Los documentos originales deben permanecer en Google Drive. Si Render reinició y el Excel local desapareció, habrá que sincronizar y generarlo nuevamente.

## Recomendación de revisión

Flucito automatiza extracción y organización, pero la V1 todavía requiere revisión humana. Antes de usar el Excel para una operación definitiva, verifica:

- folio y UUID;
- proveedor;
- código del producto;
- cantidad;
- precio y subtotal;
- fecha de emisión;
- hoja de errores.
