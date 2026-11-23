"""Conserva el resumen de compras exportado por SAE."""
from alembic import op
import sqlalchemy as sa

revision = "0003_historial_lineas_sae"
down_revision = "0002_preferencias_decision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sae_resumen_compras",
        sa.Column("clave_proveedor", sa.String(32), sa.ForeignKey("sae_proveedores.clave_proveedor", ondelete="CASCADE"), primary_key=True),
        sa.Column("lineas_frecuentes_json", sa.Text(), nullable=False),
        sa.Column("total_articulos_comprados", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("sae_resumen_compras")
