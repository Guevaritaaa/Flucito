"""Conexión de solo lectura al respaldo de SAE."""

from collections.abc import Iterator
from contextlib import contextmanager

from firebird.driver import Connection, Isolation, TraAccessMode, connect, tpb

from app.core.config import settings


class SaeNoDisponible(RuntimeError):
    """El respaldo no está listo para responder consultas."""


@contextmanager
def conectar_sae() -> Iterator[Connection]:
    password = settings.sae_firebird_password
    if not password:
        raise SaeNoDisponible("La conexión a Aspel SAE no está configurada")

    with connect(
        f"{settings.sae_firebird_host}/3050:sae_empresa02",
        user="FLUCITO_SAE_LECTOR",
        password=password,
        charset="ISO8859_1",
    ) as conexion:
        conexion.begin(tpb(Isolation.READ_COMMITTED_RECORD_VERSION, access_mode=TraAccessMode.READ))
        yield conexion


def comprobar_conexion() -> None:
    with conectar_sae() as conexion:
        fila = conexion.cursor().execute(
            "SELECT DOCUMENTOS, ULTIMO_DOCUMENTO FROM FLUCITO_SAE_CONTROL"
        ).fetchone()
        if fila is None or fila[0] <= 0 or fila[1] is None:
            raise RuntimeError("El respaldo SAE no contiene las compras esperadas")
        print(f"Firebird SAE disponible. Último documento de compra: {fila[1].isoformat()}")


if __name__ == "__main__":
    comprobar_conexion()
