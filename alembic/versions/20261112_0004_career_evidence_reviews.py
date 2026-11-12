"""Registra revisões humanas imutáveis de evidências do Career Twin.

Revision ID: 20261112_0004
Revises: 20261112_0003
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0004"
down_revision = "20261112_0003"
branch_labels = None
depends_on = None

TABLE = "career_evidence_reviews"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("career_evidence") or not inspector.has_table("users"):
        raise RuntimeError(
            "Migração de revisão interrompida: career_evidence ou users ausente."
        )
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("evidence_id", sa.Integer(), nullable=False),
            sa.Column("decision", sa.String(length=24), nullable=False),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["career_evidence.id"], ondelete="CASCADE"),
        )
    indexes = {item.get("name") for item in sa.inspect(bind).get_indexes(TABLE)}
    for name, columns in (
        ("ix_career_evidence_reviews_user_id", ["user_id"]),
        ("ix_career_evidence_reviews_evidence_id", ["evidence_id"]),
        ("ix_career_evidence_reviews_created_at", ["created_at"]),
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
            "Downgrade interrompido: revisões humanas contêm histórico. "
            "Os registros não serão apagados."
        )
    indexes = {item.get("name") for item in inspector.get_indexes(TABLE)}
    for name in (
        "ix_career_evidence_reviews_created_at",
        "ix_career_evidence_reviews_evidence_id",
        "ix_career_evidence_reviews_user_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
