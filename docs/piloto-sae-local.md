# Piloto local de Aspel SAE

Este entorno de Docker usa el respaldo transportable `backend/datos/laboratorio_sae/antigua.fbk` de la Empresa 02. Firebird 3.0.14 restaura el archivo a un volumen persistente y lo deja en modo de solo lectura. FastAPI se conecta al alias `sae_empresa02` por una red interna con la cuenta `FLUCITO_SAE_LECTOR`. El proyecto tiene su propia base SQLite de Flucito y accede a Firebird desde dentro de Docker.

## Arranque y comprobación

Con Docker Desktop activo y `backend/.env` configurado para arrancar Flucito, ejecuta desde la raíz del repositorio. El archivo privado `.env.sae.local` se crea una sola vez con dos contraseñas aleatorias y está excluido de Git.

```powershell
if (-not (Test-Path -LiteralPath '.env.sae.local')) {
    $adminPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
    $readerPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
    @("SAE_FIREBIRD_ADMIN_PASSWORD=$adminPassword", "SAE_FIREBIRD_PASSWORD=$readerPassword") |
        Set-Content -LiteralPath '.env.sae.local' -Encoding utf8
}
docker compose --env-file .env.sae.local -f compose.sae-local.yml up -d --build --wait
docker compose --env-file .env.sae.local -f compose.sae-local.yml exec flucito python -m app.services.sae.conexion
```

La comprobación consulta la vista de control desde el contenedor de FastAPI. El último documento de compra esperado es del **1 de julio de 2026**. La fecha procede de `COMPC02.FECHA_DOC` y describe hasta dónde llegan los documentos de compras del respaldo.

Para apagar el entorno conservando el corte y la base local de Flucito, usa `docker compose --env-file .env.sae.local -f compose.sae-local.yml down`. El siguiente arranque reutiliza los volúmenes. El `.fbk` se monta en solo lectura. Si está en otra ubicación, define `SAE_BACKUP_FILE` con su ruta al preparar el piloto por primera vez.

## Permisos de usuarios

Con el Compose activo, ejecuta `npm run dev` desde `frontend` y abre `http://localhost:5173`. Inicia sesión como administrador y entra en **Configuración**. La columna **Acceso a Aspel SAE** permite cambiar el permiso por cuenta, incluida tu propia cuenta. Las cuentas nuevas y existentes empiezan con **Sin acceso** hasta que un administrador lo conceda. Cambiar el permiso conserva la sesión del usuario y su rol.

## Resumen de compras

Desde `http://127.0.0.1:8000/docs`, usa **Authorize** con una cuenta que tenga acceso a Aspel SAE. En **Aspel SAE**, ejecuta `GET /api/v1/sae/resumen` con `desde=2026-06-01` y `hasta=2026-06-30`. Ambas fechas son inclusivas. Sin fechas, el resumen cubre los seis meses completos anteriores al mes de la última compra registrada. Una solicitud fuera de la cobertura devuelve las fechas disponibles. Un periodo cubierto sin compras devuelve un conteo de cero.

El resumen devuelve el conteo de documentos vigentes, los importes con impuestos en moneda del documento, la serie mensual y hasta cinco proveedores por moneda ordenados por importe. Cuenta una vez cada cabecera de `COMPC02` con estado `E` u `O`. `IMPORTE` se guarda en moneda base, por lo que el cálculo divide entre `TIPCAMB` y redondea cada documento a centavos antes de sumar. La cobertura se basa en `FECHA_DOC`. El identificador se deriva de la huella del `.fbk` y la fecha de generación del respaldo queda vacía mientras falte evidencia.

Para habilitar las vistas de compras, el primer arranque de esta fase restaura el mismo `.fbk` a un nuevo archivo dentro del volumen. El alias pasa a ese archivo y los siguientes reinicios lo reutilizan. La copia restaurada de la fase anterior queda en el volumen.

## Chat de Aspel SAE

Con acceso concedido, pulsa **Abrir chat SAE** en la barra lateral o pregunta por las compras en un chat cotidiano. En el segundo caso, el botón que aparece bajo la respuesta abre un hilo nuevo con la pregunta en el editor, lista para enviarse. Por ejemplo, pregunta «¿Cuántas compras registramos en Aspel SAE en junio de 2026?» y luego «¿Y en USD?». El chat usa el mismo servicio de métricas del resumen y admite conteos e importes agrupados por mes o proveedor, con filtros por periodo, moneda y proveedor.

Retira el permiso desde Configuración con la sesión del otro usuario abierta. Su chat SAE quedará bloqueado, incluso si conserva el enlace directo. El historial cotidiano se puede seguir abriendo. Si restituyes el permiso, el usuario recupera el historial del chat SAE.

## Panel Aspel SAE

Con una cuenta autorizada, abre **Aspel SAE** en la barra lateral de Flucito. Puedes consultar el periodo y la cobertura del respaldo, elegir moneda para los importes y revisar la tendencia mensual y los principales proveedores. El conteo general reúne todos los documentos vigentes del periodo. **Ver datos mensuales** abre la tabla que acompaña a la gráfica. **Preguntar a Flucito** lleva el periodo y la moneda del resumen a un chat SAE nuevo.

### Facturación

**Facturación** muestra las facturas vigentes y las devoluciones de venta por separado. Ambos importes incluyen impuestos y aparecen en la moneda del documento. La API `GET /api/v1/sae/facturacion` acepta las mismas fechas inclusivas que el resumen de compras y usa la cobertura de las facturas. Cuenta cada cabecera de `FACTF02` o `FACTD02` una vez. Para pasar de la moneda base a la moneda del documento, divide el importe entre `TIPCAMB` y redondea cada documento a centavos. Las devoluciones se toman de `FACTD02`. La cifra de facturación se puede usar como importe emitido. Para conciliar saldos o cobros haría falta incorporar sus propias fuentes. [Resumen de facturas de Aspel](https://saeportaldeclientes.aspel.com.mx/generar-reporte-del-resumen-de-facturas/)

El cotejo con el FDB antiguo dio 513 facturas vigentes en junio de 2026, incluidas 293 con más de una partida, y 7 canceladas quedaron fuera. Entre enero y junio hubo 2,802 facturas vigentes y 3 devoluciones. Las facturas y devoluciones de este corte están en MXN. La conversión de USD se verificó también con documentos de prueba en una base aislada.

### Inventario

**Inventario** consulta productos activos. Muestra el saldo global de `INVE02` y usa `MULT02` para el saldo y el mínimo configurados en cada almacén activo. Las claves conservan sus espacios originales para distinguir registros que SAE guarda por separado. **Sin existencia** cuenta saldos iguales o menores a cero. **Bajo mínimo** cuenta productos cuyo saldo queda por debajo de un mínimo mayor a cero. Un artículo puede aparecer en ambos conteos. [Productos por almacén en Aspel](https://saeportaldeclientes.aspel.com.mx/crear-o-dar-de-alta-productos-en-multialmacen/)

La API `GET /api/v1/sae/inventario` admite `almacen`, `articulo`, `estado` y `pagina`. El chat admite las existencias al corte, también desglosadas por almacén. La fecha que se muestra corresponde al último movimiento registrado. En el FDB antiguo se cotejaron 21,957 productos activos globales, 16,844 sin existencia y 419 bajo mínimo. Los totales por almacén usan los artículos asignados a cada uno.

El primer arranque con estas vistas restaura el mismo `.fbk` en otro archivo versionado del volumen. El alias del piloto apunta a esa restauración de solo lectura. El cotejo se hizo contra el FDB del respaldo. Queda disponible la conciliación con reportes de SAE del mismo corte cuando se cuente con ellos.
