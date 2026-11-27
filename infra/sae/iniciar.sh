#!/usr/bin/env bash
set -euo pipefail

database=/var/lib/firebird/data/sae_empresa02_compras_v1.fdb
alias_line="sae_empresa02 = $database"
if ! grep -Fxq "$alias_line" /opt/firebird/databases.conf; then
    sed -i '/^sae_empresa02 = /d' /opt/firebird/databases.conf
    printf '\n%s\n' "$alias_line" >> /opt/firebird/databases.conf
fi

# La cuenta remota recibe únicamente los permisos de lectura concedidos abajo.
password_sql=${SAE_FIREBIRD_PASSWORD//\'/\'\'}
isql -b -q -user SYSDBA security.db <<SQL
CREATE OR ALTER USER FLUCITO_SAE_LECTOR PASSWORD '$password_sql' REVOKE ADMIN ROLE;
SQL

if [[ ! -f "$database" ]]; then
    staging=$(mktemp -d "${database}.restore.XXXXXX")
    trap 'rm -f -- "$staging/sae.fdb"; rmdir -- "$staging"' EXIT
    restored="$staging/sae.fdb"
    gbak -create -mode read_write -user SYSDBA /pilot/antigua.fbk "$restored"
    read -r sha256 _ < <(sha256sum /pilot/antigua.fbk)
    isql -b -q -user SYSDBA "$restored" <<'SQL'
CREATE VIEW FLUCITO_SAE_CONTROL (DOCUMENTOS, ULTIMO_DOCUMENTO) AS
SELECT COUNT(*), CAST(MAX(FECHA_DOC) AS DATE) FROM COMPC02;
GRANT SELECT ON FLUCITO_SAE_CONTROL TO USER FLUCITO_SAE_LECTOR;
COMMIT;
SQL
    sed "s/@SHA256@/$sha256/g" /pilot/compras.sql | isql -b -q -user SYSDBA "$restored"
    gfix -user SYSDBA -mode read_only "$restored"
    chown firebird:firebird "$restored"
    chmod 640 "$restored"
    mv -- "$restored" "$database"
    rmdir -- "$staging"
    trap - EXIT
fi

exec entrypoint.sh firebird
