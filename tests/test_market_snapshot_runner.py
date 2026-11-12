import json
from datetime import datetime, timedelta

from jobfinder import market_snapshot_runner
from jobfinder.market import taxonomy_version
from jobfinder.market_service import EXTRACTOR_VERSION
from jobfinder.models import MarketAnalysisRun


def _completed_run(db, completed_at, *, days=30, taxonomy=None, extractor=None):
    run = MarketAnalysisRun(
        level_scope="both",
        filters_json=json.dumps({"days": days, "min_jobs": 30}),
        taxonomy_version=taxonomy or taxonomy_version(),
        extractor_version=extractor or EXTRACTOR_VERSION,
        status="completed",
        created_at=completed_at,
        completed_at=completed_at,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_runner_creates_first_snapshot_when_none_exists(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        market_snapshot_runner, "index_unprocessed_jobs",
        lambda session: calls.append("index") or {"jobs_indexed": 3},
    )
    monkeypatch.setattr(
        market_snapshot_runner, "create_market_snapshot",
        lambda session, **kwargs: calls.append(kwargs) or {"run_id": 10, "status": "completed"},
    )

    result = market_snapshot_runner.run_snapshot_if_due(
        db, now=datetime(2026, 11, 12, 9, 0, 0)
    )

    assert result["status"] == "created"
    assert calls == ["index", {"level_scope": "both", "days": 30, "min_jobs": 30}]


def test_runner_skips_comparable_snapshot_younger_than_15_days(db, monkeypatch):
    now = datetime(2026, 11, 12, 9, 0, 0)
    run = _completed_run(db, now - timedelta(days=4))
    monkeypatch.setattr(
        market_snapshot_runner, "index_unprocessed_jobs",
        lambda session: (_ for _ in ()).throw(AssertionError("não deveria indexar")),
    )
    monkeypatch.setattr(
        market_snapshot_runner, "create_market_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("não deveria criar snapshot")),
    )

    result = market_snapshot_runner.run_snapshot_if_due(db, now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "snapshot_recent"
    assert result["latest_run_id"] == run.id
    assert result["next_due_at"] == (now - timedelta(days=4) + timedelta(days=15)).isoformat()


def test_runner_creates_new_snapshot_after_15_days(db, monkeypatch):
    now = datetime(2026, 11, 12, 9, 0, 0)
    _completed_run(db, now - timedelta(days=16))
    monkeypatch.setattr(
        market_snapshot_runner, "index_unprocessed_jobs",
        lambda session: {"jobs_indexed": 1},
    )
    monkeypatch.setattr(
        market_snapshot_runner, "create_market_snapshot",
        lambda session, **kwargs: {"run_id": 11, "status": "completed", **kwargs},
    )

    result = market_snapshot_runner.run_snapshot_if_due(db, now=now)

    assert result["status"] == "created"
    assert result["snapshot"]["run_id"] == 11


def test_runner_rebuilds_immediately_when_taxonomy_changes(db, monkeypatch):
    now = datetime(2026, 11, 12, 9, 0, 0)
    _completed_run(db, now - timedelta(days=1), taxonomy="old-taxonomy")
    monkeypatch.setattr(
        market_snapshot_runner, "index_unprocessed_jobs",
        lambda session: {"jobs_indexed": 0},
    )
    monkeypatch.setattr(
        market_snapshot_runner, "create_market_snapshot",
        lambda session, **kwargs: {"run_id": 12, "status": "completed"},
    )

    result = market_snapshot_runner.run_snapshot_if_due(db, now=now)

    assert result["status"] == "created"
