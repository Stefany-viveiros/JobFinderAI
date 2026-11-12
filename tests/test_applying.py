import pytest
from types import SimpleNamespace
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
    assert applying.extract_apply_email("Envie seu currículo para: <b>rh@empresa.com.br</b> ou noreply@x.com") == "rh@empresa.com.br"
    assert applying.extract_apply_email("Contato geral: contato@empresa.com.br") is None
    assert applying.extract_apply_email("Suporte técnico: suporte@empresa.com.br") is None
    assert applying.extract_apply_email("só noreply@x.com") is None
    attempt = applying.prepare_attempt(db, make_job(db), ready_profile)
    assert attempt.channel == "email" and attempt.recipient == "vagas@acme.com" and attempt.status == "prepared"


def test_email_channel_unavailable_without_smtp(db, ready_profile):
    attempt = applying.prepare_attempt(db, make_job(db), ready_profile)
    assert attempt.channel == "manual" and "SMTP" in attempt.detail

def test_multitenant_email_is_blocked_until_user_resume_can_be_attached(db, ready_profile, test_user, monkeypatch):
    from cryptography.fernet import Fernet
    from jobfinder.models import ApplicationAttempt, SmtpAccount
    from jobfinder.smtp_credentials import encrypt_password

    monkeypatch.setenv("MULTITENANT_READY", "true")
    monkeypatch.setenv("SMTP_CREDENTIALS_KEY", Fernet.generate_key().decode("ascii"))
    account = SmtpAccount(
        user_id=test_user.id, host="smtp.example.com", port=587,
        username="ana@example.com", encrypted_password=encrypt_password("app-password"),
        from_email="ana@example.com", use_tls=True,
    )
    db.add(account)
    db.commit()

    job = make_job(db)
    available, reason = applying.email_channel_available(job, user_id=test_user.id, db=db)
    assert available is False
    assert "currículo" in reason
    assert "Perfil profissional" in reason

    # Mesmo uma tentativa antiga não pode contornar a regra nem anexar CV global.
    attempt = ApplicationAttempt(
        user_id=test_user.id, job_id=job.id, status="prepared", channel="email",
        recipient="vagas@acme.com", subject="Candidatura", message="Olá",
    )
    db.add(attempt)
    db.commit()
    with pytest.raises(applying.ApplyError, match="currículo"):
        applying.send_attempt(db, attempt, user_id=test_user.id)
    assert attempt.status == "prepared"


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


def test_cover_letter_uses_multiple_structured_degrees_and_experience(db):
    from jobfinder.models import Profile, Education, Experience, PortfolioProject
    job = make_job(db, title="Estágio Backend Python", company="ACME")
    profile = Profile(
        id=1,
        name="Ana Teste",
        technologies="Python",
        educations=[
            Education(course="Engenharia da Computação", institution="FAM", status="Em andamento"),
            Education(course="ADS", institution="Cruzeiro do Sul", status="Em andamento"),
        ],
        experiences=[
            Experience(company="Empresa A", role="Analista", description="Análise de processos"),
        ],
        portfolio_projects=[
            PortfolioProject(name="Sistema Web", technologies="Python, React", description="Aplicação acadêmica"),
        ],
    )
    _, body = applying.build_cover_letter(job, profile)
    assert "Engenharia da Computação" in body and "ADS" in body
    assert "Empresa A" in body and "Analista" in body
    assert "Sistema Web" in body and "Python, React" in body


def test_smtp_transport_uses_implicit_ssl_on_port_465(monkeypatch):
    calls = []
    class FakeSMTP:
        def __init__(self, host, port, timeout, context):
            calls.append(("connect_ssl", host, port, context))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): calls.append(("ehlo",))
        def login(self, username, password): calls.append(("login", username))
        def send_message(self, msg): calls.append(("send",))
    monkeypatch.setattr(applying.smtplib, "SMTP_SSL", FakeSMTP)
    applying._deliver(applying.EmailMessage(), {"host":"smtp.example.com","port":465,"username":"u","password":"p","use_tls":True})
    assert calls[0][:3] == ("connect_ssl", "smtp.example.com", 465)
    assert ("login", "u") in calls and ("send",) in calls
    assert not any(call[0] == "starttls" for call in calls)


def test_smtp_transport_uses_starttls_on_port_587(monkeypatch):
    calls = []
    class FakeSMTP:
        def __init__(self, host, port, timeout): calls.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): calls.append(("ehlo",))
        def starttls(self, context): calls.append(("starttls", context))
        def login(self, username, password): calls.append(("login", username))
        def send_message(self, msg): calls.append(("send",))
    monkeypatch.setattr(applying.smtplib, "SMTP", FakeSMTP)
    applying._deliver(applying.EmailMessage(), {"host":"smtp.example.com","port":587,"username":"u","password":"p","use_tls":True})
    assert calls[0] == ("connect", "smtp.example.com", 587)
    assert any(call[0] == "starttls" for call in calls)
    assert ("login", "u") in calls and ("send",) in calls


def test_smtp_transport_refuses_plaintext_authentication():
    with pytest.raises(applying.ApplyError, match="sem TLS"):
        applying._deliver(applying.EmailMessage(), {"host":"smtp.example.com","port":25,"username":"u","password":"p","use_tls":False})
