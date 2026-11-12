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
