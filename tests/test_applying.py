import pytest
from sqlalchemy import select

from jobfinder import applying
from jobfinder.models import Application
from tests.conftest import make_job


def test_cover_letter_uses_only_profile_facts(db, ready_profile):
    job = make_job(db, description="Buscamos Python, Java e Kubernetes. vagas@acme.com")
    subject, body = applying.build_cover_letter(job, ready_profile)
    assert "Python" in body and "Ana Teste" in subject
    assert "Java" not in body and "Kubernetes" not in body      # não está no perfil -> não aparece
    assert "FastAPI" not in body                                 # está no perfil, mas não na vaga


def test_prepare_requires_complete_profile(db):
    job = make_job(db)
    from jobfinder.service import get_profile
    with pytest.raises(applying.ApplyError, match="perfil"):
        applying.prepare_attempt(db, job, get_profile(db))


def test_prepare_never_marks_as_sent(db, ready_profile):
    job = make_job(db, description="sem contato")
    attempt = applying.prepare_attempt(db, job, ready_profile)
    assert attempt.status == "manual_required" and attempt.sent_at is None
    assert job.url in attempt.detail
    assert db.scalar(select(Application)) is None                # nenhuma "candidatura enviada" criada
    with pytest.raises(applying.ApplyError):                     # não duplica tentativa em aberto
        applying.prepare_attempt(db, job, ready_profile)


def test_email_channel_requires_published_address_and_smtp(db, ready_profile, smtp_on):
    assert applying.extract_apply_email("contato: <b>rh@empresa.com.br</b> ou noreply@x.com") == "rh@empresa.com.br"
    assert applying.extract_apply_email("só noreply@x.com") is None
    attempt = applying.prepare_attempt(db, make_job(db), ready_profile)
    assert attempt.channel == "email" and attempt.recipient == "vagas@acme.com" and attempt.status == "prepared"


def test_email_channel_unavailable_without_smtp(db, ready_profile):
    attempt = applying.prepare_attempt(db, make_job(db), ready_profile)
    assert attempt.channel == "manual" and "SMTP" in attempt.detail


def test_send_success_records_sent_and_pipeline(db, ready_profile, smtp_on):
    job = make_job(db)
    attempt = applying.prepare_attempt(db, job, ready_profile)
    applying.send_attempt(db, attempt)
    assert attempt.status == "sent" and attempt.sent_at
    assert len(smtp_on) == 1 and smtp_on[0]["To"] == "vagas@acme.com"
    assert db.scalar(select(Application).where(Application.job_id == job.id)).status == "Candidatura enviada"


def test_send_failure_is_failed_not_sent(db, ready_profile, smtp_on, monkeypatch):
    def boom(msg):
        raise ConnectionRefusedError("smtp caiu")
    monkeypatch.setattr(applying, "_deliver", boom)
    job = make_job(db)
    attempt = applying.send_attempt(db, applying.prepare_attempt(db, job, ready_profile))
    assert attempt.status == "failed" and "smtp caiu" in attempt.detail and attempt.sent_at is None
    assert db.scalar(select(Application)) is None


def test_daily_limit_blocks_extra_sends(db, ready_profile, smtp_on):
    a1 = applying.prepare_attempt(db, make_job(db), ready_profile)
    a2 = applying.prepare_attempt(db, make_job(db), ready_profile)
    applying.send_attempt(db, a1, daily_limit=1)
    assert applying.sent_today_count(db) == 1
    with pytest.raises(applying.ApplyError, match="Limite diário"):
        applying.send_attempt(db, a2, daily_limit=1)
    assert a2.status == "prepared" and len(smtp_on) == 1


def test_manual_confirmation_is_the_only_manual_path_to_sent(db, ready_profile):
    job = make_job(db, description="sem contato")
    applying.prepare_attempt(db, job, ready_profile)
    attempt = applying.confirm_manual_send(db, job)
    assert attempt.status == "sent" and attempt.channel == "manual_confirmed"
    assert applying.sent_today_count(db) == 0                    # manual não consome limite automático
    with pytest.raises(applying.ApplyError):
        applying.confirm_manual_send(db, job)


def test_cancel_sent_attempt_is_refused(db, ready_profile, smtp_on):
    attempt = applying.send_attempt(db, applying.prepare_attempt(db, make_job(db), ready_profile))
    with pytest.raises(applying.ApplyError):
        applying.cancel_attempt(db, attempt)
