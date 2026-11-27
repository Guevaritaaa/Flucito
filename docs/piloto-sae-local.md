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
