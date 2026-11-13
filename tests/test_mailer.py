import pytest
from datetime import date, datetime
from types import SimpleNamespace
from jobfinder.mailer import build_email, pending_tasks


def test_email_mentions_deadline_and_overdue():
    task=SimpleNamespace(title="Enviar currículo",due_date=date(2026,1,1),priority="Alta")
    plain,html=build_email([task],today=date(2026,1,2))
    assert "Enviar currículo" in plain and "VENCIDA" in plain
    assert "Alta" in html


def test_legacy_reminder_runner_is_blocked_when_multiuser_gate_is_enabled(monkeypatch):
    from jobfinder.mailer import send_daily_reminder

    monkeypatch.setenv("MULTITENANT_READY", "true")
    result = send_daily_reminder(object())

    assert result["status"] == "blocked"
    assert "envio individual por conta" in result["detail"]



def test_legacy_reminder_runner_blocks_before_database_when_multitenant(monkeypatch):
    from jobfinder import reminder_runner

    monkeypatch.setenv("MULTITENANT_READY", "true")
    monkeypatch.setattr(reminder_runner, "init_db", lambda: pytest.fail("não deve inicializar o banco"))
    monkeypatch.setattr(reminder_runner, "SessionLocal", lambda: pytest.fail("não deve abrir sessão"))

    result = reminder_runner.main()
    assert result["status"] == "blocked"
    assert "envio individual por conta" in result["detail"]
