"""Agendamento idempotente de snapshots públicos de inteligência de mercado.

O runner pode ser chamado diariamente por cron/GitHub Actions; só cria um snapshot
quando não há um snapshot comparável concluído nos últimos 15 dias. Ele nunca
executa migrações: o banco precisa estar previamente atualizado pelo deploy.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select

from .db import SessionLocal, engine
from .market import taxonomy_version
from .market_service import EXTRACTOR_VERSION, create_market_snapshot, index_unprocessed_jobs
from .models import MarketAnalysisRun


REQUIRED_MARKET_TABLES = {
    "jobs",
    "skills",
    "job_skills",
    "job_skill_extractions",
    "market_analysis_runs",
    "market_skill_metrics",
    "market_skill_pairs",
}


def validate_market_schema(connection) -> dict:
    """Falha antes de escrever se o banco não estiver na revisão Alembic atual."""
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    current = MigrationContext.configure(connection).get_current_revision()
    missing = sorted(REQUIRED_MARKET_TABLES - set(inspect(connection).get_table_names()))

    if len(heads) != 1 or current != heads[0]:
        raise RuntimeError(
            "Banco de inteligência de mercado fora da revisão Alembic atual. "
            "Aplique as migrações no processo de deploy antes de executar o snapshot."
        )
    if missing:
        raise RuntimeError(
            "Schema de inteligência de mercado incompleto; tabelas ausentes: "
            + ", ".join(missing)
        )
    return {"revision": current, "tables": "ok"}


def run_snapshot_if_due(
    db,
    *,
    now: datetime | None = None,
    interval_days: int = 15,
    days: int = 30,
    min_jobs: int = 30,
) -> dict:
    """Cria snapshot comparável no máximo uma vez por janela de 15 dias."""
    now = now or datetime.utcnow()
    latest = db.scalar(
        select(MarketAnalysisRun)
        .where(
            MarketAnalysisRun.status == "completed",
            MarketAnalysisRun.level_scope == "both",
        )
        .order_by(
            func.coalesce(MarketAnalysisRun.completed_at, MarketAnalysisRun.created_at).desc(),
            MarketAnalysisRun.id.desc(),
        )
        .limit(1)
    )
    if latest is not None:
        try:
            filters = json.loads(latest.filters_json or "{}")
        except (TypeError, ValueError):
            filters = {}
        completed_at = latest.completed_at or latest.created_at
        same_definition = (
            int(filters.get("days", 0) or 0) == days
            and latest.taxonomy_version == taxonomy_version()
            and latest.extractor_version == EXTRACTOR_VERSION
        )
        if same_definition and completed_at and now - completed_at < timedelta(days=interval_days):
            next_due = completed_at + timedelta(days=interval_days)
            return {
                "status": "skipped",
                "reason": "snapshot_recent",
                "latest_run_id": latest.id,
                "last_completed_at": completed_at.isoformat(),
                "next_due_at": next_due.isoformat(),
            }

    indexing = index_unprocessed_jobs(db)
    snapshot = create_market_snapshot(
        db, level_scope="both", days=days, min_jobs=min_jobs
    )
    return {
        "status": "created",
        "indexing": indexing,
        "snapshot": snapshot,
    }


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit(
            "DATABASE_URL ausente. Configure o segredo MARKET_DATABASE_URL no GitHub Actions."
        )
    # O runner não chama init_db(): nenhuma migração ou criação de tabela é
    # executada automaticamente por um job agendado.
    with engine.connect() as connection:
        schema = validate_market_schema(connection)
    with SessionLocal() as db:
        result = run_snapshot_if_due(db)
    print(json.dumps({"schema": schema, "result": result}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
