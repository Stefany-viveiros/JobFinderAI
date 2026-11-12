"""Add account-scoped application status history.

Revision ID: 20261112_0002
Revises: 20261102_0001
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0002"
down_revision = "20261102_0001"
branch_labels = None
depends_on = None

TABLE = "application_events"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Instalações antigas sem a tabela principal dependem do bootstrap/create_all.
    if not inspector.has_table("applications"):
        return
    if not inspector.has_table("users"):
        raise RuntimeError(
            "Migração de histórico interrompida: tabela users ausente. "
            "Crie/valide o schema de autenticação antes de registrar eventos."
        )

    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("application_id", sa.Integer(), nullable=False),
            sa.Column("previous_status", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("new_status", sa.String(length=80), nullable=False),
            sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        )

    inspector = sa.inspect(bind)
    indexes = {
        item.get("name")
        for item in inspector.get_indexes(TABLE)
    }
    if "ix_application_events_user_id" not in indexes:
        op.create_index("ix_application_events_user_id", TABLE, ["user_id"])
    if "ix_application_events_application_id" not in indexes:
        op.create_index("ix_application_events_application_id", TABLE, ["application_id"])
    if "ix_application_events_occurred_at" not in indexes:
        op.create_index("ix_application_events_occurred_at", TABLE, ["occurred_at"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return

    # Não apagar eventos históricos em rollback. Se a tabela recebeu dados,
    # interrompe o downgrade e exige uma migração substituta de preservação.
    event_count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one()
    if event_count:
        raise RuntimeError(
            "Downgrade interrompido: application_events contém histórico de candidaturas. "
            "Os dados não serão apagados; crie uma migração de compatibilidade antes de reverter."
        )

    indexes = {
        item.get("name")
        for item in inspector.get_indexes(TABLE)
    }
    for name in (
        "ix_application_events_occurred_at",
        "ix_application_events_application_id",
        "ix_application_events_user_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
