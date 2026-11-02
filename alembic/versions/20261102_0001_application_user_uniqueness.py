"""Replace global application uniqueness with per-user uniqueness.

Revision ID: 20261102_0001
Revises:
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_0001"
down_revision = None
branch_labels = None
depends_on = None

TABLE = "applications"
COMPOSITE_NAME = "uq_user_application_job"


def _schema_state():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return [], []
    constraints = inspector.get_unique_constraints(TABLE)
    indexes = [
        item for item in inspector.get_indexes(TABLE)
        if item.get("unique")
    ]
    return constraints, indexes


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        # Instalações novas podem executar create_all antes ou depois do Alembic.
        return

    constraints, indexes = _schema_state()
    duplicate = bind.execute(sa.text(
        "SELECT user_id, job_id, COUNT(*) AS total "
        "FROM applications WHERE user_id IS NOT NULL "
        "GROUP BY user_id, job_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            "Migração interrompida: existem candidaturas duplicadas para o mesmo usuário e vaga. "
            "Revise os registros antes de aplicar a constraint composta."
        )

    global_constraints = [
        item for item in constraints
        if sorted(item.get("column_names") or []) == ["job_id"]
    ]
    global_indexes = [
        item for item in indexes
        if sorted(item.get("column_names") or []) == ["job_id"]
    ]
    has_composite = any(
        sorted(item.get("column_names") or []) == ["job_id", "user_id"]
        for item in constraints + indexes
    )

    if bind.dialect.name == "sqlite":
        # SQLite não permite DROP CONSTRAINT diretamente: batch recria a tabela,
        # preservando as linhas e demais colunas. O naming convention dá nome
        # estável às constraints UNIQUE antigas que foram criadas sem nome.
        if global_constraints or global_indexes or not has_composite:
            convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
            with op.batch_alter_table(
                TABLE, recreate="always", naming_convention=convention
            ) as batch:
                for item in global_constraints:
                    name = item.get("name") or "uq_applications_job_id"
                    batch.drop_constraint(name, type_="unique")
                for item in global_indexes:
                    batch.drop_index(item["name"])
                if not has_composite:
                    batch.create_unique_constraint(
                        COMPOSITE_NAME, ["user_id", "job_id"]
                    )
        return

    for item in global_constraints:
        if not item.get("name"):
            raise RuntimeError(
                "Migração interrompida: constraint UNIQUE global sem nome no PostgreSQL."
            )
        op.drop_constraint(item["name"], TABLE, type_="unique")
    for item in global_indexes:
        op.drop_index(item["name"], table_name=TABLE)
    if not has_composite:
        op.create_unique_constraint(
            COMPOSITE_NAME, TABLE, ["user_id", "job_id"]
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return

    constraints, indexes = _schema_state()
    already_global = any(
        sorted(item.get("column_names") or []) == ["job_id"]
        for item in constraints + indexes
    )
    has_composite_constraints = [
        item for item in constraints
        if sorted(item.get("column_names") or []) == ["job_id", "user_id"]
    ]
    has_composite_indexes = [
        item for item in indexes
        if sorted(item.get("column_names") or []) == ["job_id", "user_id"]
    ]
    duplicate = bind.execute(sa.text(
        "SELECT job_id, COUNT(*) AS total FROM applications "
        "GROUP BY job_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            "Downgrade impossível: existem candidaturas da mesma vaga em contas diferentes. "
            "A constraint global antiga não pode ser restaurada sem perda de dados."
        )

    if bind.dialect.name == "sqlite":
        convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
        with op.batch_alter_table(
            TABLE, recreate="always", naming_convention=convention
        ) as batch:
            for item in has_composite_constraints:
                batch.drop_constraint(
                    item.get("name") or COMPOSITE_NAME, type_="unique"
                )
            for item in has_composite_indexes:
                batch.drop_index(item["name"])
            if not already_global:
                batch.create_unique_constraint(
                    "uq_applications_job_id", ["job_id"]
                )
        return

    for item in has_composite_constraints:
        op.drop_constraint(item["name"], TABLE, type_="unique")
    for item in has_composite_indexes:
        op.drop_index(item["name"], table_name=TABLE)
    if not already_global:
        op.create_unique_constraint(
            "uq_applications_job_id", TABLE, ["job_id"]
        )
