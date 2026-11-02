"""Isola o banco: nenhum teste toca em data/jobfinder.db."""
import dataclasses
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="jobfinder-test-")
_TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()
if _TEST_POSTGRES_URL:
    # No job PostgreSQL, a suíte inteira (incluindo APIs) usa o banco efêmero.
    os.environ["DATABASE_URL"] = _TEST_POSTGRES_URL
else:
    os.environ["JOBFINDER_DB_PATH"] = os.path.join(_TMP, "test.db")  # antes de importar jobfinder

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from jobfinder import applying  # noqa: E402
from jobfinder.db import Base, SessionLocal, engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db):
    from jobfinder.models import User
    from jobfinder.api import password_hasher
    user = User(
        email="tester@example.com",
        email_normalized="tester@example.com",
        full_name="Usuário de Teste",
        password_hash=password_hasher.hash("SenhaSegura123!"),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def ready_profile(db, test_user):
    from jobfinder.service import get_profile
    p = get_profile(db, user_id=test_user.id)
    p.name, p.course, p.institution = "Ana Teste", "Análise e Desenvolvimento de Sistemas", "Faculdade Exemplo"
    p.technologies, p.skills = "Python, FastAPI, Git", "APIs REST"
    p.interests, p.location, p.modality = "Backend, Estágio", "Brasil", "Remoto"
    db.commit()
    return p


@pytest.fixture
def smtp_on(monkeypatch):
    """Simula SMTP configurado e captura mensagens em vez de enviar."""
    sent = []
    cfg = dataclasses.replace(applying.settings, smtp_host="smtp.test", smtp_from="ana@test.dev",
                              smtp_username="u", smtp_password="p", cv_path="")
    monkeypatch.setattr(applying, "settings", cfg)
    monkeypatch.setattr(applying, "_deliver", lambda msg: sent.append(msg))
    return sent


def make_job(db, **kw):
    from jobfinder.models import Job, JobMatch, User
    data = dict(source="Teste", title="Estágio Backend Python", company="ACME",
                description="Python e FastAPI. Envie currículo para vagas@acme.com", location="Remoto",
                modality="Remoto", job_type="Estágio", url=f"https://x.test/{os.urandom(4).hex()}",
                compatibility=80, level="estagio")
    data.update(kw)
    job = Job(**data)
    db.add(job)
    db.flush()
    # Em testes autenticados, cria o score privado da conta de teste.
    user = db.scalar(select(User).order_by(User.id))
    if user is not None:
        db.add(JobMatch(
            user_id=user.id, job_id=job.id,
            compatibility=float(data.get("compatibility") or 0),
            match_reasons=data.get("match_reasons") or "",
            missing_reasons=data.get("missing_reasons") or "",
            is_favorite=bool(data.get("is_favorite", False)),
            is_archived=bool(data.get("is_archived", False)),
        ))
    db.commit()
    db.refresh(job)
    return job
