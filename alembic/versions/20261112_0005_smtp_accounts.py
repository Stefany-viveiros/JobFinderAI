"""Adiciona conexões SMTP individuais com senha cifrada.

Revision ID: 20261112_0005
Revises: 20261112_0004
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0005"
down_revision = "20261112_0004"
branch_labels = None
depends_on = None

TABLE = "smtp_accounts"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        raise RuntimeError("Migração SMTP interrompida: tabela users ausente.")
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("host", sa.String(length=255), nullable=False),
            sa.Column("port", sa.Integer(), nullable=False, server_default="587"),
            sa.Column("username", sa.String(length=320), nullable=False),
            sa.Column("encrypted_password", sa.Text(), nullable=False),
            sa.Column("from_email", sa.String(length=320), nullable=False),
            sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", name="uq_smtp_accounts_user_id"),
        )
    indexes = {item.get("name") for item in sa.inspect(bind).get_indexes(TABLE)}
    if "ix_smtp_accounts_user_id" not in indexes:
        op.create_index("ix_smtp_accounts_user_id", TABLE, ["user_id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one()
    if count:
        raise RuntimeError(
            "Downgrade SMTP interrompido: há credenciais individuais cifradas. "
            "Remova-as por procedimento autenticado antes de reverter; os dados não serão apagados."
        )
    indexes = {item.get("name") for item in inspector.get_indexes(TABLE)}
    if "ix_smtp_accounts_user_id" in indexes:
        op.drop_index("ix_smtp_accounts_user_id", table_name=TABLE)
    op.drop_table(TABLE)
