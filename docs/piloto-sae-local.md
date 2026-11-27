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
