from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError


def test_legacy_global_application_constraint_is_migrated_to_per_user(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    engine = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    applications = sa.Table(
        "applications",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("job_id", sa.Integer, nullable=False),
        sa.Column("status", sa.String(80), nullable=False, server_default="Candidatura enviada"),
        sa.UniqueConstraint("job_id", name="uq_applications_job_id"),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            applications.insert(),
            [{"id": 1, "user_id": 10, "job_id": 100},
             {"id": 2, "user_id": 20, "job_id": 200}],
        )

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    unique_sets = {
        tuple(sorted(item.get("column_names") or ()))
        for item in inspector.get_unique_constraints("applications")
    }
    assert ("job_id", "user_id") in unique_sets
    assert ("job_id",) not in unique_sets

    with engine.begin() as connection:
        # Duas contas podem se candidatar à mesma vaga.
        connection.execute(
            applications.insert(),
            [{"id": 3, "user_id": 10, "job_id": 300},
             {"id": 4, "user_id": 20, "job_id": 300}],
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                applications.insert(),
                {"id": 5, "user_id": 10, "job_id": 300},
            )
    engine.dispose()


def test_migration_refuses_duplicate_applications_for_same_user(tmp_path, monkeypatch):
    database = tmp_path / "duplicates.db"
    engine = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    applications = sa.Table(
        "applications",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("job_id", sa.Integer, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            applications.insert(),
            [{"id": 1, "user_id": 10, "job_id": 300},
             {"id": 2, "user_id": 10, "job_id": 300}],
        )

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="candidaturas duplicadas"):
        command.upgrade(config, "head")
    engine.dispose()


def test_postgresql_migration_replaces_global_unique_constraint(monkeypatch):
    import os
    from uuid import uuid4

    postgres_url = os.getenv("TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("TEST_POSTGRES_URL não configurada; teste executado no CI com PostgreSQL.")

    from sqlalchemy.engine import make_url

    admin_engine = sa.create_engine(postgres_url)
    schema = f"jobfinder_mig_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    scoped_url = make_url(postgres_url).set(
        query={"options": f"-csearch_path={schema}"}
    )
    engine = sa.create_engine(scoped_url)
    try:
        metadata = sa.MetaData()
        applications = sa.Table(
            "applications",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("job_id", sa.Integer, nullable=False),
            sa.Column("status", sa.String(80), nullable=False, server_default="Candidatura enviada"),
            sa.UniqueConstraint("job_id", name="uq_legacy_applications_job_id"),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                applications.insert(),
                [{"id": 1, "user_id": 10, "job_id": 100},
                 {"id": 2, "user_id": 20, "job_id": 200}],
            )

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        config = Config(str(config_path))
        config.set_main_option("sqlalchemy.url", str(scoped_url).replace("%", "%%"))
        monkeypatch.setenv("DATABASE_URL", str(scoped_url))
        command.upgrade(config, "head")

        inspector = sa.inspect(engine)
        unique_sets = {
            tuple(sorted(item.get("column_names") or ()))
            for item in inspector.get_unique_constraints("applications")
        }
        assert ("job_id", "user_id") in unique_sets
        assert ("job_id",) not in unique_sets

        with engine.begin() as connection:
            connection.execute(
                applications.insert(),
                [{"id": 3, "user_id": 10, "job_id": 300},
                 {"id": 4, "user_id": 20, "job_id": 300}],
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    applications.insert(),
                    {"id": 5, "user_id": 10, "job_id": 300},
                )

        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT COUNT(*) FROM applications")
            ).scalar_one() == 4
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
