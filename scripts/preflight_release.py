"""Diagnóstico somente de leitura antes de uma implantação do JobFinder AI.

Uso:
  DATABASE_URL='postgresql+psycopg://...' python scripts/preflight_release.py
  DATABASE_URL='...' python scripts/preflight_release.py --require-multitenant

O script nunca aplica migrações, cria tabelas ou altera registros.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_TABLES = (
    "user_sessions",
    "password_reset_tokens",
    "profile",
    "job_matches",
    "applications",
    "application_events",
    "tasks",
    "notification_log",
    "agent_settings",
    "application_attempts",
    "development_plan_items",
    "skill_assessment_attempts",
    "career_evidence",
    "career_evidence_reviews",
    "smtp_accounts",
    "user_resumes",
)


def safe_database_label(url: str) -> str:
    """Retorna apenas dialeto/host/database, nunca usuário ou senha."""
    parsed = make_url(url)
    host = parsed.host or ("local" if parsed.drivername.startswith("sqlite") else "unknown")
    database = Path(parsed.database).name if parsed.database else "unknown"
    return f"{parsed.drivername}://{host}/{database}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-multitenant",
        action="store_true",
        help="Executa também o gate completo de schema multiusuário (somente leitura).",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print(json.dumps({
            "status": "blocked",
            "reason": "DATABASE_URL ausente; informe explicitamente o banco de staging.",
            "mutations_performed": False,
        }, ensure_ascii=False))
        return 2

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    engine = create_engine(database_url, pool_pre_ping=True)
    report: dict = {
        "database": safe_database_label(database_url),
        "mutations_performed": False,
        "checks": {},
        "warnings": [],
    }
    failures: list[str] = []

    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            elif connection.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON")

            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            missing_tables = sorted(set(PRIVATE_TABLES) - tables)
            report["checks"]["required_private_tables"] = {
                "status": "failed" if missing_tables else "ok",
                "missing": missing_tables,
            }
            if missing_tables:
                failures.append("Tabelas privadas ausentes.")

            current = MigrationContext.configure(connection).get_current_revision()
            report["checks"]["alembic"] = {
                "current_revision": current,
                "head_revisions": heads,
                "status": "ok" if current in heads and len(heads) == 1 else "failed",
            }
            if current not in heads or len(heads) != 1:
                failures.append("Banco não está na única revisão head do Alembic.")

            ownership: dict[str, dict] = {}
            for table in PRIVATE_TABLES:
                if table not in tables:
                    continue
                columns = {column["name"] for column in inspector.get_columns(table)}
                if "user_id" not in columns:
                    ownership[table] = {"status": "failed", "reason": "coluna user_id ausente"}
                    failures.append(f"{table}.user_id ausente.")
                    continue
                fk_ok = any(
                    fk.get("constrained_columns") == ["user_id"]
                    and fk.get("referred_table") == "users"
                    and fk.get("referred_columns") == ["id"]
                    for fk in inspector.get_foreign_keys(table)
                )
                if "users" not in tables:
                    null_or_orphan = None
                else:
                    null_or_orphan = connection.execute(text(
                        f'SELECT COUNT(*) FROM "{table}" t '
                        'LEFT JOIN users u ON u.id = t.user_id '
                        'WHERE t.user_id IS NULL OR u.id IS NULL'
                    )).scalar_one()
                row = {
                    "status": "ok" if fk_ok and null_or_orphan == 0 else "failed",
                    "owner_foreign_key": fk_ok,
                    "unowned_or_orphan_records": null_or_orphan,
                }
                ownership[table] = row
                if row["status"] != "ok":
                    failures.append(f"{table}: FK ausente ou registros sem proprietário válido.")
            report["checks"]["ownership"] = ownership

            if args.require_multitenant and not failures:
                # Validador adicional do próprio produto; só consulta schema e dados.
                os.environ["DATABASE_URL"] = database_url
                from jobfinder.db import validate_multitenant_schema

                validate_multitenant_schema()
                report["checks"]["multitenant_gate"] = {"status": "ok"}
            elif args.require_multitenant:
                report["checks"]["multitenant_gate"] = {
                    "status": "not_run",
                    "reason": "Corrija primeiro as falhas estruturais e de titularidade.",
                }

        report["status"] = "blocked" if failures else "ready_for_review"
        report["failures"] = failures
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if failures else 0
    except Exception as exc:
        # Não imprime URL, credenciais, SQL nem dados de usuários.
        report["status"] = "error"
        report["error_type"] = type(exc).__name__
        report["error"] = "Falha na verificação. Consulte logs seguros do ambiente."
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
