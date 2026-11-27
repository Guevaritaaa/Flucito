"""Distingue los chats cotidianos de las conversaciones de Aspel SAE."""

import sqlalchemy as sa
from alembic import context, op

revision = "0005_tipo_conversacion"
down_revision = "0004_acceso_sae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and any(
        column["name"] == "tipo" for column in sa.inspect(op.get_bind()).get_columns("conversaciones")
    ):
        return
    op.add_column("conversaciones", sa.Column("tipo", sa.String(16), server_default="general", nullable=False))


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("La reversión requiere comprobar que la base no contiene chats de Aspel SAE.")
    if op.get_bind().execute(sa.text("SELECT 1 FROM conversaciones WHERE tipo = 'sae' LIMIT 1")).first():
        raise RuntimeError("La base contiene chats de Aspel SAE que necesitan conservar su control de acceso.")
    op.drop_column("conversaciones", "tipo")
