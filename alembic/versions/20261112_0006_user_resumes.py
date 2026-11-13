"""Adiciona armazenamento cifrado de currículo por usuário.

Revision ID: 20261112_0006
Revises: 20261112_0005
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0006"
down_revision = "20261112_0005"
branch_labels = None
depends_on = None

TABLE = "user_resumes"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        raise RuntimeError("Migração de currículo interrompida: tabela users ausente.")
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("encrypted_content", sa.Text(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", name="uq_user_resumes_user_id"),
        )
    indexes = {item.get("name") for item in sa.inspect(bind).get_indexes(TABLE)}
    if "ix_user_resumes_user_id" not in indexes:
        op.create_index("ix_user_resumes_user_id", TABLE, ["user_id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one()
    if count:
        raise RuntimeError(
            "Downgrade interrompido: há currículos cifrados por usuário. "
            "Remova-os por procedimento autenticado antes de reverter."
        )
    indexes = {item.get("name") for item in inspector.get_indexes(TABLE)}
    if "ix_user_resumes_user_id" in indexes:
        op.drop_index("ix_user_resumes_user_id", table_name=TABLE)
    op.drop_table(TABLE)
