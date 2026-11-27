"""Añade el permiso individual de acceso a Aspel SAE."""

import sqlalchemy as sa
from alembic import context, op

revision = "0004_acceso_sae"
down_revision = "0003_historial_lineas_sae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and any(
        column["name"] == "acceso_sae" for column in sa.inspect(op.get_bind()).get_columns("usuarios")
    ):
        return

    op.add_column("usuarios", sa.Column("acceso_sae", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("usuarios", "acceso_sae")
