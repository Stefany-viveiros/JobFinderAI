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
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
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
        sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
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

        # O downgrade global seria destrutivo: duas contas possuem a mesma vaga.
        with pytest.raises(RuntimeError, match="Downgrade impossível"):
            command.downgrade(config, "base")
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT COUNT(*) FROM applications")
            ).scalar_one() == 4
        constraints_after_refusal = {
            tuple(sorted(item.get("column_names") or []))
            for item in sa.inspect(engine).get_unique_constraints("applications")
        }
        assert ("job_id", "user_id") in constraints_after_refusal
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()



def test_application_history_migration_creates_account_scoped_event_table(tmp_path, monkeypatch):
    database = tmp_path / "application-history.db"
    engine = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    applications = sa.Table(
        "applications",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("job_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
    )
    metadata.create_all(engine)

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert inspector.has_table("application_events")
    columns = {item["name"]: item for item in inspector.get_columns("application_events")}
    assert columns["user_id"]["nullable"] is False
    assert columns["application_id"]["nullable"] is False
    indexes = {item["name"] for item in inspector.get_indexes("application_events")}
    assert {
        "ix_application_events_user_id",
        "ix_application_events_application_id",
        "ix_application_events_occurred_at",
    }.issubset(indexes)

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(sa.text("INSERT INTO applications (id, user_id, job_id) VALUES (10, 1, 99)"))
        connection.execute(sa.text(
            "INSERT INTO application_events "
            "(id, user_id, application_id, previous_status, new_status, source, note, occurred_at) "
            "VALUES (100, 1, 10, '', 'Candidatura enviada', 'manual_confirmed', '', CURRENT_TIMESTAMP)"
        ))
        count = connection.execute(sa.text("SELECT COUNT(*) FROM application_events")).scalar_one()
        assert count == 1

    # Um rollback com histórico existente deve falhar sem remover a tabela nem os eventos.
    with pytest.raises(RuntimeError, match="Os dados não serão apagados"):
        command.downgrade(config, "20261102_0001")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT COUNT(*) FROM application_events")).scalar_one() == 1
    assert sa.inspect(engine).has_table("application_events")
    engine.dispose()


def test_postgresql_application_history_migration_preserves_events_on_rollback(monkeypatch):
    import os
    from uuid import uuid4
    from sqlalchemy.engine import make_url

    postgres_url = os.getenv("TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("TEST_POSTGRES_URL não configurada; teste executado no CI com PostgreSQL.")

    admin_engine = sa.create_engine(postgres_url)
    schema = f"jobfinder_events_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    scoped_url = make_url(postgres_url).set(
        query={"options": f"-csearch_path={schema}"}
    )
    engine = sa.create_engine(scoped_url)
    try:
        metadata = sa.MetaData()
        sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
        applications = sa.Table(
            "applications", metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("job_id", sa.Integer, nullable=False),
            sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
        )
        metadata.create_all(engine)

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        config = Config(str(config_path))
        config.set_main_option("sqlalchemy.url", str(scoped_url).replace("%", "%%"))
        monkeypatch.setenv("DATABASE_URL", str(scoped_url))
        command.upgrade(config, "head")

        inspector = sa.inspect(engine)
        assert inspector.has_table("application_events")
        foreign_keys = inspector.get_foreign_keys("application_events")
        assert any(fk["constrained_columns"] == ["user_id"] and fk["referred_table"] == "users" for fk in foreign_keys)
        assert any(fk["constrained_columns"] == ["application_id"] and fk["referred_table"] == "applications" for fk in foreign_keys)

        with engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
            connection.execute(sa.text("INSERT INTO applications (id, user_id, job_id) VALUES (10, 1, 99)"))
            connection.execute(sa.text(
                "INSERT INTO application_events "
                "(id, user_id, application_id, previous_status, new_status, source, note, occurred_at) "
                "VALUES (100, 1, 10, '', 'Candidatura enviada', 'manual_confirmed', '', CURRENT_TIMESTAMP)"
            ))

        with pytest.raises(RuntimeError, match="Os dados não serão apagados"):
            command.downgrade(config, "20261102_0001")
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT COUNT(*) FROM application_events")).scalar_one() == 1
        assert sa.inspect(engine).has_table("application_events")

        with engine.begin() as connection:
            connection.execute(sa.text("DELETE FROM application_events WHERE id = 100"))
        command.downgrade(config, "20261102_0001")
        assert not sa.inspect(engine).has_table("application_events")
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def test_career_evidence_migration_preserves_versioned_history_on_rollback(tmp_path, monkeypatch):
    database = tmp_path / "career-evidence.db"
    engine = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "applications", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("job_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
    )
    metadata.create_all(engine)

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert inspector.has_table("career_evidence")
    columns = {item["name"]: item for item in inspector.get_columns("career_evidence")}
    assert columns["user_id"]["nullable"] is False
    assert columns["evidence_hash"]["nullable"] is False
    assert columns["verification_level"]["nullable"] is False
    indexes = {item["name"] for item in inspector.get_indexes("career_evidence")}
    assert {
        "ix_career_evidence_user_id",
        "ix_career_evidence_skill_name",
        "ix_career_evidence_source_key",
        "ix_career_evidence_is_active",
    }.issubset(indexes)
    foreign_keys = inspector.get_foreign_keys("career_evidence")
    assert any(
        fk["constrained_columns"] == ["user_id"] and fk["referred_table"] == "users"
        for fk in foreign_keys
    )

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(sa.text(
            "INSERT INTO career_evidence "
            "(id, user_id, skill_name, category, source_type, source_key, source_id, "
            "source_label, excerpt, evidence_hash, verification_level, is_active, created_at) "
            "VALUES (1, 1, 'Python', 'language', 'self_declared', 'legacy:skills', NULL, "
            "'Habilidades declaradas', 'Python', :digest, 'self_reported', 1, CURRENT_TIMESTAMP)"
        ), {"digest": "a" * 64})

    with pytest.raises(RuntimeError, match="Os dados não serão apagados"):
        command.downgrade(config, "20261112_0002")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT COUNT(*) FROM career_evidence")).scalar_one() == 1
    assert sa.inspect(engine).has_table("career_evidence")
    engine.dispose()


def test_postgresql_career_evidence_migration_preserves_history_on_rollback(monkeypatch):
    import os
    from uuid import uuid4
    from sqlalchemy.engine import make_url

    postgres_url = os.getenv("TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("TEST_POSTGRES_URL não configurada; teste executado no CI com PostgreSQL.")

    admin_engine = sa.create_engine(postgres_url)
    schema = f"jobfinder_career_evidence_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    scoped_url = make_url(postgres_url).set(
        query={"options": f"-csearch_path={schema}"}
    )
    engine = sa.create_engine(scoped_url)
    try:
        metadata = sa.MetaData()
        sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
        sa.Table(
            "applications", metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("job_id", sa.Integer, nullable=False),
            sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
        )
        metadata.create_all(engine)

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        config = Config(str(config_path))
        config.set_main_option("sqlalchemy.url", str(scoped_url).replace("%", "%%"))
        monkeypatch.setenv("DATABASE_URL", str(scoped_url))
        command.upgrade(config, "head")

        inspector = sa.inspect(engine)
        assert inspector.has_table("career_evidence")
        foreign_keys = inspector.get_foreign_keys("career_evidence")
        assert any(
            fk["constrained_columns"] == ["user_id"] and fk["referred_table"] == "users"
            for fk in foreign_keys
        )

        with engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
            connection.execute(sa.text(
                "INSERT INTO career_evidence "
                "(id, user_id, skill_name, category, source_type, source_key, source_id, "
                "source_label, excerpt, evidence_hash, verification_level, is_active, created_at) "
                "VALUES (1, 1, 'Python', 'language', 'self_declared', 'legacy:skills', NULL, "
                "'Habilidades declaradas', 'Python', :digest, 'self_reported', true, CURRENT_TIMESTAMP)"
            ), {"digest": "b" * 64})

        with pytest.raises(RuntimeError, match="Os dados não serão apagados"):
            command.downgrade(config, "20261112_0002")
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT COUNT(*) FROM career_evidence")).scalar_one() == 1
        assert sa.inspect(engine).has_table("career_evidence")

        with engine.begin() as connection:
            connection.execute(sa.text("DELETE FROM career_evidence WHERE id = 1"))
        command.downgrade(config, "20261112_0002")
        assert not sa.inspect(engine).has_table("career_evidence")
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()

def test_career_evidence_review_migration_preserves_human_history_on_rollback(tmp_path, monkeypatch):
    database = tmp_path / "career-evidence-reviews.db"
    engine = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "applications", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("job_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
    )
    metadata.create_all(engine)

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert inspector.has_table("career_evidence_reviews")
    columns = {item["name"]: item for item in inspector.get_columns("career_evidence_reviews")}
    assert columns["user_id"]["nullable"] is False
    assert columns["evidence_id"]["nullable"] is False
    indexes = {item["name"] for item in inspector.get_indexes("career_evidence_reviews")}
    assert {
        "ix_career_evidence_reviews_user_id",
        "ix_career_evidence_reviews_evidence_id",
        "ix_career_evidence_reviews_created_at",
    }.issubset(indexes)

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(sa.text(
            "INSERT INTO career_evidence "
            "(id, user_id, skill_name, category, source_type, source_key, source_id, "
            "source_label, excerpt, evidence_hash, verification_level, is_active, created_at) "
            "VALUES (1, 1, 'Python', 'language', 'self_declared', 'legacy:skills', NULL, "
            "'Habilidades declaradas', 'Python', :digest, 'self_reported', 1, CURRENT_TIMESTAMP)"
        ), {"digest": "c" * 64})
        connection.execute(sa.text(
            "INSERT INTO career_evidence_reviews "
            "(id, user_id, evidence_id, decision, note, created_at) "
            "VALUES (1, 1, 1, 'confirmed', 'Origem revisada', CURRENT_TIMESTAMP)"
        ))

    with pytest.raises(RuntimeError, match="Os registros não serão apagados"):
        command.downgrade(config, "20261112_0003")
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT COUNT(*) FROM career_evidence_reviews")
        ).scalar_one() == 1
    assert sa.inspect(engine).has_table("career_evidence_reviews")

    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM career_evidence_reviews WHERE id = 1"))
    command.downgrade(config, "20261112_0003")
    assert not sa.inspect(engine).has_table("career_evidence_reviews")
    engine.dispose()


def test_smtp_accounts_migration_is_account_scoped_and_refuses_data_loss(tmp_path, monkeypatch):
    database = tmp_path / "smtp-accounts.db"
    engine = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "applications", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("job_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
    )
    metadata.create_all(engine)

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert inspector.has_table("smtp_accounts")
    columns = {item["name"]: item for item in inspector.get_columns("smtp_accounts")}
    assert columns["user_id"]["nullable"] is False
    assert columns["encrypted_password"]["nullable"] is False
    assert "password" not in columns
    assert "encrypted_password" in columns
    unique_sets = {
        tuple(sorted(item.get("column_names") or ()))
        for item in inspector.get_unique_constraints("smtp_accounts")
    }
    assert ("user_id",) in unique_sets
    assert any(
        fk["constrained_columns"] == ["user_id"]
        and fk["referred_table"] == "users"
        for fk in inspector.get_foreign_keys("smtp_accounts")
    )

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id) VALUES (1), (2)"))
        connection.execute(sa.text(
            "INSERT INTO smtp_accounts "
            "(id, user_id, host, port, username, encrypted_password, from_email, use_tls, created_at, updated_at) "
            "VALUES (1, 1, 'smtp.example.test', 587, 'user@example.test', 'ciphertext-only', "
            "'user@example.test', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO smtp_accounts "
                "(id, user_id, host, port, username, encrypted_password, from_email, use_tls, created_at, updated_at) "
                "VALUES (2, 1, 'smtp.example.test', 587, 'other@example.test', 'ciphertext-only', "
                "'other@example.test', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))

    with pytest.raises(RuntimeError, match="os dados não serão apagados"):
        command.downgrade(config, "20261112_0004")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT COUNT(*) FROM smtp_accounts")).scalar_one() == 1
    assert sa.inspect(engine).has_table("smtp_accounts")
    engine.dispose()



def test_user_resume_migration_is_private_and_refuses_data_loss(tmp_path, monkeypatch):
    database = tmp_path / "user-resumes.db"
    engine = sa.create_engine(f"sqlite:///{database}")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "applications", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("job_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
    )
    metadata.create_all(engine)

    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert inspector.has_table("user_resumes")
    columns = {item["name"]: item for item in inspector.get_columns("user_resumes")}
    assert columns["user_id"]["nullable"] is False
    assert columns["encrypted_content"]["nullable"] is False
    assert columns["sha256"]["nullable"] is False
    unique_sets = {
        tuple(sorted(item.get("column_names") or ()))
        for item in inspector.get_unique_constraints("user_resumes")
    }
    assert ("user_id",) in unique_sets
    assert any(
        fk["constrained_columns"] == ["user_id"] and fk["referred_table"] == "users"
        for fk in inspector.get_foreign_keys("user_resumes")
    )

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(sa.text(
            "INSERT INTO user_resumes "
            "(id, user_id, filename, content_type, encrypted_content, sha256, created_at, updated_at) "
            "VALUES (1, 1, 'resume.pdf', 'application/pdf', 'ciphertext-only', :digest, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"digest": "d" * 64})

    with pytest.raises(RuntimeError, match="currículos cifrados por usuário"):
        command.downgrade(config, "20261112_0005")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT COUNT(*) FROM user_resumes")).scalar_one() == 1
    assert sa.inspect(engine).has_table("user_resumes")
    engine.dispose()


def test_postgresql_smtp_accounts_migration_is_account_scoped_and_preserves_credentials(monkeypatch):
    import os
    from uuid import uuid4
    from sqlalchemy.engine import make_url

    postgres_url = os.getenv("TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("TEST_POSTGRES_URL não configurada; teste executado no CI com PostgreSQL.")
    admin_engine = sa.create_engine(postgres_url)
    schema = f"jobfinder_smtp_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = make_url(postgres_url).set(
        query={"options": f"-csearch_path={schema}"}
    )
    engine = sa.create_engine(scoped_url)
    try:
        metadata = sa.MetaData()
        sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
        sa.Table(
            "applications", metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("job_id", sa.Integer, nullable=False),
            sa.UniqueConstraint("user_id", "job_id", name="uq_user_application_job"),
        )
        metadata.create_all(engine)

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        config = Config(str(config_path))
        config.set_main_option("sqlalchemy.url", str(scoped_url).replace("%", "%%"))
        monkeypatch.setenv("DATABASE_URL", str(scoped_url))
        command.upgrade(config, "head")

        inspector = sa.inspect(engine)
        assert inspector.has_table("smtp_accounts")
        unique_sets = {
            tuple(sorted(item.get("column_names") or ()))
            for item in inspector.get_unique_constraints("smtp_accounts")
        }
        assert ("user_id",) in unique_sets
        assert any(
            fk["constrained_columns"] == ["user_id"]
            and fk["referred_table"] == "users"
            for fk in inspector.get_foreign_keys("smtp_accounts")
        )
        with engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO users (id) VALUES (1), (2)"))
            connection.execute(sa.text(
                "INSERT INTO smtp_accounts "
                "(id, user_id, host, port, username, encrypted_password, from_email, use_tls, created_at, updated_at) "
                "VALUES (1, 1, 'smtp.example.test', 587, 'user@example.test', 'ciphertext-only', "
                "'user@example.test', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(sa.text(
                    "INSERT INTO smtp_accounts "
                    "(id, user_id, host, port, username, encrypted_password, from_email, use_tls, created_at, updated_at) "
                    "VALUES (2, 1, 'smtp.example.test', 587, 'other@example.test', 'ciphertext-only', "
                    "'other@example.test', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))
        with pytest.raises(RuntimeError, match="os dados não serão apagados"):
            command.downgrade(config, "20261112_0004")
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT COUNT(*) FROM smtp_accounts")).scalar_one() == 1
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
