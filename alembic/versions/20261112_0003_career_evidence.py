"""Cria o ledger persistente e versionado de evidências do Career Twin.

Revision ID: 20261112_0003
Revises: 20261112_0002
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0003"
down_revision = "20261112_0002"
branch_labels = None
depends_on = None

TABLE = "career_evidence"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        raise RuntimeError(
            "Migração do ledger interrompida: tabela users ausente. "
            "Valide o schema de autenticação antes de registrar evidências."
        )
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("skill_name", sa.String(length=120), nullable=False),
            sa.Column("category", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("source_type", sa.String(length=50), nullable=False),
            sa.Column("source_key", sa.String(length=240), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("source_label", sa.String(length=300), nullable=False, server_default=""),
            sa.Column("excerpt", sa.Text(), nullable=False, server_default=""),
            sa.Column("evidence_hash", sa.String(length=64), nullable=False),
            sa.Column("verification_level", sa.String(length=30), nullable=False, server_default="self_reported"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("superseded_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "user_id", "source_key", "skill_name", "evidence_hash",
                name="uq_career_evidence_version",
            ),
        )
    inspector = sa.inspect(bind)
    indexes = {item.get("name") for item in inspector.get_indexes(TABLE)}
    for name, columns in (
        ("ix_career_evidence_user_id", ["user_id"]),
        ("ix_career_evidence_skill_name", ["skill_name"]),
        ("ix_career_evidence_source_key", ["source_key"]),
        ("ix_career_evidence_is_active", ["is_active"]),
    ):
        if name not in indexes:
            op.create_index(name, TABLE, columns)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one()
    if count:
        raise RuntimeError(
            "Downgrade interrompido: career_evidence contém histórico versionado. "
            "Os dados não serão apagados; crie uma migração de compatibilidade antes de reverter."
        )
    indexes = {item.get("name") for item in inspector.get_indexes(TABLE)}
    for name in (
        "ix_career_evidence_is_active",
        "ix_career_evidence_source_key",
        "ix_career_evidence_skill_name",
        "ix_career_evidence_user_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
