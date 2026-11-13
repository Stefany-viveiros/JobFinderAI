import os
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
# JOBFINDER_DB_PATH permite isolar o banco (usado nos testes).
DB_PATH = Path(os.getenv("JOBFINDER_DB_PATH") or (DATA_DIR / "jobfinder.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
DB_URL = DATABASE_URL or f"sqlite:///{DB_PATH.as_posix()}"
engine_options = {"pool_pre_ping": True}
if DB_URL.startswith("sqlite:"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DB_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# (tabela, coluna, DDL). create_all() não altera tabelas existentes, então
# colunas novas são adicionadas aqui sem apagar nenhum dado.
MIGRATIONS = [
    ("jobs", "dedupe_key", "VARCHAR(400)"),
    ("jobs", "level", "VARCHAR(20) DEFAULT ''"),
    # Colunas de propriedade começam nullable para preservar os bancos existentes.
    # Os dados legados permanecem sem proprietário até o bootstrap administrativo
    # seguro atribuí-los explicitamente; nenhuma conta nova os recebe por padrão.
    ("profile", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("applications", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("tasks", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("notification_log", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("agent_settings", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("application_attempts", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("development_plan_items", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("skill_assessment_attempts", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
]


def backup_database() -> Path | None:
    """Cópia consistente do banco antes de qualquer migração estrutural."""
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return None
    target_dir = DB_PATH.parent / "backups"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"{DB_PATH.stem}-{datetime.now():%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def _missing_columns():
    insp = inspect(engine)
    missing = []
    for table, column, ddl in MIGRATIONS:
        if insp.has_table(table) and column not in {c["name"] for c in insp.get_columns(table)}:
            missing.append((table, column, ddl))
    return missing



def validate_multitenant_schema(connection=None) -> None:
    """Valida propriedade, FKs e unicidade usando a conexão fornecida, quando houver."""
    if connection is None:
        with engine.connect() as owned_connection:
            return validate_multitenant_schema(owned_connection)
    inspector = inspect(connection)
    user_scoped_tables = (
        "user_sessions", "password_reset_tokens", "profile", "job_matches",
        "applications", "application_events", "tasks", "notification_log",
        "agent_settings", "application_attempts", "development_plan_items",
        "skill_assessment_attempts", "career_evidence", "career_evidence_reviews", "smtp_accounts", "user_resumes",
    )

    for table in user_scoped_tables:
        if not inspector.has_table(table):
            raise RuntimeError(f"Schema SaaS inválido: tabela {table} ausente.")
        column_details = {column["name"]: column for column in inspector.get_columns(table)}
        if "user_id" not in column_details:
            raise RuntimeError(f"Schema SaaS inválido: coluna {table}.user_id ausente.")
        if column_details["user_id"]["nullable"]:
            raise RuntimeError(
                f"Schema SaaS inválido: {table}.user_id ainda aceita NULL. "
                "Aplique a migração de propriedade antes de liberar o acesso."
            )
        owner_fk_exists = any(
            fk.get("constrained_columns") == ["user_id"]
            and fk.get("referred_table") == "users"
            and fk.get("referred_columns") == ["id"]
            for fk in inspector.get_foreign_keys(table)
        )
        if not owner_fk_exists:
            raise RuntimeError(
                f"Schema SaaS inválido: {table}.user_id precisa referenciar users.id."
            )
        unowned = connection.execute(
            text(f'SELECT COUNT(*) FROM "{table}" WHERE user_id IS NULL')
        ).scalar_one()
        if unowned:
            raise RuntimeError(
                f"Schema SaaS inválido: {table} contém {unowned} registro(s) sem proprietário. "
                "Resolva os dados legados por procedimento explícito antes de liberar o acesso."
            )

    def unique_sets(table: str) -> set[tuple[str, ...]]:
        result = {
            tuple(sorted(item.get("column_names") or ()))
            for item in inspector.get_unique_constraints(table)
        }
        result.update(
            tuple(sorted(index.get("column_names") or ()))
            for index in inspector.get_indexes(table)
            if index.get("unique")
        )
        return result

    # O ledger e as revisões são dados pessoais: validar também a relação
    # entre a conta da revisão e a conta proprietária da evidência.
    for table in ("career_evidence", "career_evidence_reviews"):
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        if columns["user_id"]["nullable"]:
            raise RuntimeError(
                f"Schema SaaS inválido: {table}.user_id não pode aceitar NULL."
            )
    review_fks = inspector.get_foreign_keys("career_evidence_reviews")
    if not any(
        fk.get("constrained_columns") == ["evidence_id"]
        and fk.get("referred_table") == "career_evidence"
        and fk.get("referred_columns") == ["id"]
        for fk in review_fks
    ):
        raise RuntimeError(
            "Schema SaaS inválido: career_evidence_reviews.evidence_id precisa referenciar career_evidence.id."
        )
    mismatched_reviews = connection.execute(text(
        "SELECT COUNT(*) FROM career_evidence_reviews r "
        "LEFT JOIN career_evidence e ON e.id = r.evidence_id "
        "WHERE e.id IS NULL OR r.user_id != e.user_id"
    )).scalar_one()
    if mismatched_reviews:
        raise RuntimeError(
            f"Schema SaaS inválido: {mismatched_reviews} revisão(ões) sem evidência correspondente ou vinculada(s) a outra conta."
        )

    # O histórico de candidatura também é privado: não basta o evento
    # pertencer a um usuário válido; ele precisa pertencer ao dono da candidatura.
    mismatched_application_events = connection.execute(text(
        "SELECT COUNT(*) FROM application_events ev "
        "LEFT JOIN applications a ON a.id = ev.application_id "
        "WHERE a.id IS NULL OR ev.user_id != a.user_id"
    )).scalar_one()
    if mismatched_application_events:
        raise RuntimeError(
            f"Schema SaaS inválido: {mismatched_application_events} evento(s) de candidatura "
            "sem candidatura correspondente ou vinculados a outra conta."
        )

    for table in ("applications", "job_matches"):
        constraints = unique_sets(table)
        if ("job_id", "user_id") not in constraints:
            raise RuntimeError(
                f"Schema SaaS inválido: falta unicidade composta (user_id, job_id) em {table}."
            )
        if ("job_id",) in constraints:
            raise RuntimeError(
                f"Schema SaaS inválido: existe unicidade global antiga em {table}.job_id."
            )

    for table in ("smtp_accounts", "user_resumes"):
        if ("user_id",) not in unique_sets(table):
            raise RuntimeError(
                f"Schema SaaS inválido: falta unicidade por usuário em {table}.user_id."
            )

    for table in ("profile", "agent_settings"):
        if ("user_id",) not in unique_sets(table):
            raise RuntimeError(
                f"Schema SaaS inválido: falta unicidade por usuário em {table}.user_id."
            )



def _ensure_postgres_multitenant_constraints() -> None:
    """Reconcilia constraints legadas com o modelo multiusuário sem tocar nos registros."""
    if engine.dialect.name != "postgresql":
        return

    replacements = (
        # Removem unicidade global antiga e passam a limitar por conta.
        ("applications", "applications_job_id_key", "uq_user_application_job", ("user_id", "job_id")),
        ("notification_log", "uq_task_recipient_day", "uq_user_task_recipient_day", ("user_id", "task_id", "recipient", "send_date")),
    )
    required = (
        ("profile", "uq_profile_user", ("user_id",)),
        ("agent_settings", "uq_agent_settings_user", ("user_id",)),
        ("smtp_accounts", "uq_smtp_accounts_user", ("user_id",)),
        ("user_resumes", "uq_user_resumes_user", ("user_id",)),
    )

    with engine.begin() as connection:
        # Evita que dois workers tentem criar as mesmas constraints ao iniciar.
        connection.execute(text("SELECT pg_advisory_xact_lock(731904221)"))
        inspector = inspect(connection)

        for table, legacy_name, new_name, columns in replacements:
            existing = {item["name"] for item in inspector.get_unique_constraints(table)}
            if legacy_name in existing:
                connection.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{legacy_name}"'))
            if new_name not in existing:
                column_sql = ", ".join(f'"{column}"' for column in columns)
                connection.execute(text(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{new_name}" UNIQUE ({column_sql})'
                ))
            inspector = inspect(connection)

        for table, constraint_name, columns in required:
            existing = {item["name"] for item in inspector.get_unique_constraints(table)}
            if constraint_name not in existing:
                column_sql = ", ".join(f'"{column}"' for column in columns)
                connection.execute(text(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint_name}" UNIQUE ({column_sql})'
                ))
            inspector = inspect(connection)

        # As tabelas legadas tinham user_id nullable. Antes de liberar o SaaS,
        # recusa a migração se houver órfãos e só então torna a propriedade obrigatória.
        owner_tables = (
            "profile", "applications", "tasks", "notification_log",
            "agent_settings", "application_attempts", "development_plan_items",
            "skill_assessment_attempts",
        )
        for table in owner_tables:
            null_count = connection.execute(
                text(f'SELECT COUNT(*) FROM "{table}" WHERE user_id IS NULL')
            ).scalar_one()
            if null_count:
                raise RuntimeError(
                    f"Migração multiusuário interrompida: {table} contém "
                    f"{null_count} registro(s) sem proprietário."
                )
            column = next(
                item for item in inspect(connection).get_columns(table)
                if item["name"] == "user_id"
            )
            if column["nullable"]:
                connection.execute(
                    text(f'ALTER TABLE "{table}" ALTER COLUMN user_id SET NOT NULL')
                )


def init_db():
    from . import models  # noqa: F401
    from .filters import dedupe_key, classify_level

    # Detecta alterações estruturais antes de create_all. O backup é feito
    # somente quando há colunas legadas a migrar, evitando uma cópia a cada
    # inicialização (inclusive em reinícios do worker e testes de idempotência).
    missing = _missing_columns()
    if (
        engine.dialect.name == "sqlite"
        and DB_PATH.exists()
        and DB_PATH.stat().st_size
        and missing
    ):
        backup_database()

    # Cria primeiro tabelas novas (especialmente users) para que FKs das
    # colunas adicionadas abaixo funcionem também no PostgreSQL.
    Base.metadata.create_all(bind=engine)
    _ensure_postgres_multitenant_constraints()
    if missing:
        with engine.begin() as conn:
            for table, column, ddl in missing:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_dedupe_key ON jobs (dedupe_key)"))
        # Preenche metadados das vagas já existentes (sem tocar nos demais campos).
        rows = conn.execute(text(
            "SELECT id, title, company, description, job_type FROM jobs "
            "WHERE level IS NULL OR level = '' OR dedupe_key IS NULL"
        )).all()
        for row in rows:
            conn.execute(
                text("UPDATE jobs SET level=:level, dedupe_key=:key WHERE id=:id"),
                {"id": row.id, "level": classify_level(row.title, row.description, row.job_type) or "outro",
                 "key": dedupe_key(row.title, row.company)},
            )
