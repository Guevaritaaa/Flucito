"""Esquema inicial de Flucito en PostgreSQL: usuarios, conversaciones, catalogo SAE y almacen.

Revision ID: 0001_esquema_inicial
Revises: 
Create Date: 2026-11-10 19:50:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_esquema_inicial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("nombre_completo", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("rol", sa.String(length=32), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_login", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usuarios_username", "usuarios", ["username"], unique=True)

    op.create_table(
        "conversaciones",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizada_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversaciones_usuario_id", "conversaciones", ["usuario_id"], unique=False)

    op.create_table(
        "mensajes_chat",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversacion_id", sa.String(length=128), nullable=False),
        sa.Column("rol", sa.String(length=32), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("metadatos_json", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversacion_id"], ["conversaciones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mensajes_chat_conversacion_id", "mensajes_chat", ["conversacion_id"], unique=False)

    op.create_table(
        "confirmaciones_pendientes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversacion_id", sa.String(length=128), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("datos_json", sa.Text(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_confirmaciones_pendientes_conversacion_id",
        "confirmaciones_pendientes",
        ["conversacion_id"],
        unique=True,
    )
    op.create_index(
        "ix_confirmaciones_pendientes_usuario_id",
        "confirmaciones_pendientes",
        ["usuario_id"],
        unique=False,
    )

    op.create_table(
        "sae_lineas",
        sa.Column("clave_linea", sa.String(length=32), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=False),
        sa.Column("estatus", sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint("clave_linea"),
    )

    op.create_table(
        "sae_proveedores",
        sa.Column("clave_proveedor", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("rfc", sa.String(length=32), nullable=False),
        sa.Column("estatus", sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint("clave_proveedor"),
    )
    op.create_index("ix_sae_proveedores_rfc", "sae_proveedores", ["rfc"], unique=False)

    op.create_table(
        "sae_articulos",
        sa.Column("clave_articulo", sa.String(length=64), nullable=False),
        sa.Column("descripcion", sa.String(length=500), nullable=False),
        sa.Column("clave_linea", sa.String(length=32), nullable=True),
        sa.Column("unidad_entrada", sa.String(length=32), nullable=False),
        sa.Column("cve_sat", sa.String(length=32), nullable=False),
        sa.Column("cve_unidad", sa.String(length=32), nullable=False),
        sa.Column("ultimo_costo", sa.Float(), nullable=False),
        sa.Column("estatus", sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint("clave_articulo"),
    )
    op.create_index("ix_sae_articulos_clave_linea", "sae_articulos", ["clave_linea"], unique=False)

    op.create_table(
        "sae_claves_alternas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("clave_alterna", sa.String(length=64), nullable=False),
        sa.Column("clave_articulo", sa.String(length=64), nullable=False),
        sa.Column("clave_proveedor", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sae_claves_alternas_clave_alterna", "sae_claves_alternas", ["clave_alterna"], unique=False)
    op.create_index("ix_sae_claves_alternas_clave_articulo", "sae_claves_alternas", ["clave_articulo"], unique=False)

    op.create_table(
        "sae_historial_compras",
        sa.Column("clave_proveedor", sa.String(length=32), nullable=False),
        sa.Column("lineas_compradas_json", sa.Text(), nullable=False),
        sa.Column("articulos_comprados_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("clave_proveedor"),
    )

    op.create_table(
        "factores_linea",
        sa.Column("clave_linea", sa.String(length=64), nullable=False),
        sa.Column("nombre_factor", sa.String(length=64), nullable=False),
        sa.Column("es_personalizado", sa.Boolean(), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("clave_linea"),
    )

    op.create_table(
        "reportes_almacen",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fecha_carpeta", sa.String(length=32), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("total_articulos", sa.Integer(), nullable=False),
        sa.Column("resumen_json", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reportes_almacen_fecha_carpeta", "reportes_almacen", ["fecha_carpeta"], unique=False)
    op.create_index("ix_reportes_almacen_usuario_id", "reportes_almacen", ["usuario_id"], unique=False)

    op.create_table(
        "detalle_entradas_almacen",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reporte_id", sa.Integer(), nullable=False),
        sa.Column("clave_articulo", sa.String(length=64), nullable=False),
        sa.Column("descripcion", sa.String(length=500), nullable=False),
        sa.Column("linea", sa.String(length=64), nullable=False),
        sa.Column("clave_proveedor", sa.String(length=64), nullable=False),
        sa.Column("cantidad", sa.Float(), nullable=False),
        sa.Column("precio_compra", sa.Float(), nullable=False),
        sa.Column("factor_aplicado", sa.String(length=64), nullable=False),
        sa.Column("origen_clave", sa.String(length=64), nullable=False),
        sa.Column("origen_linea", sa.String(length=64), nullable=False),
        sa.Column("origen_proveedor", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["reporte_id"], ["reportes_almacen.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detalle_entradas_almacen_reporte_id", "detalle_entradas_almacen", ["reporte_id"], unique=False)
    op.create_index("ix_detalle_entradas_almacen_clave_articulo", "detalle_entradas_almacen", ["clave_articulo"], unique=False)

    op.create_table(
        "archivos_sincronizados_drive",
        sa.Column("drive_file_id", sa.String(length=128), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("fecha_carpeta", sa.String(length=32), nullable=False),
        sa.Column("md5_checksum", sa.String(length=128), nullable=False),
        sa.Column("procesado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("drive_file_id"),
    )


def downgrade() -> None:
    op.drop_table("archivos_sincronizados_drive")
    op.drop_table("detalle_entradas_almacen")
    op.drop_table("reportes_almacen")
    op.drop_table("factores_linea")
    op.drop_table("sae_historial_compras")
    op.drop_table("sae_claves_alternas")
    op.drop_table("sae_articulos")
    op.drop_table("sae_proveedores")
    op.drop_table("sae_lineas")
    op.drop_table("confirmaciones_pendientes")
    op.drop_table("mensajes_chat")
    op.drop_table("conversaciones")
    op.drop_table("usuarios")
