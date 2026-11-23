"""Preferencias personales de decisiones guiadas."""
from alembic import op
import sqlalchemy as sa

revision = "0002_preferencias_decision"
down_revision = "0001_esquema_inicial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("preferencias_decision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clave", sa.String(128), nullable=False),
        sa.Column("respuesta_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("usuario_id", "clave"))
    op.create_index("ix_preferencias_decision_usuario_id", "preferencias_decision", ["usuario_id"])


def downgrade():
    op.drop_table("preferencias_decision")
