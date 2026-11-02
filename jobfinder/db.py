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



def validate_multitenant_schema() -> None:
    """Impede liberar o SaaS se candidaturas ainda tiverem unicidade global por vaga."""
    inspector = inspect(engine)
    if not inspector.has_table("applications"):
        raise RuntimeError("Schema SaaS inválido: tabela applications ausente.")

    unique_sets = {
        tuple(sorted(item.get("column_names") or ()))
        for item in inspector.get_unique_constraints("applications")
    }
    unique_sets.update(
        tuple(sorted(index.get("column_names") or ()))
        for index in inspector.get_indexes("applications")
        if index.get("unique")
    )
    if ("user_id", "job_id") not in unique_sets:
        raise RuntimeError(
            "Schema SaaS inválido: falta unicidade composta (user_id, job_id) em applications."
        )
    if ("job_id",) in unique_sets:
        raise RuntimeError(
            "Schema SaaS inválido: existe unicidade global antiga em applications.job_id. "
            "Migre a constraint antes de ativar MULTITENANT_READY."
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
