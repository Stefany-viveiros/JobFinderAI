"""Isola o banco: nenhum teste toca em data/jobfinder.db."""
import dataclasses
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="jobfinder-test-")
os.environ["JOBFINDER_DB_PATH"] = os.path.join(_TMP, "test.db")  # antes de importar jobfinder

import pytest  # noqa: E402

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
def ready_profile(db):
    from jobfinder.service import get_profile
    p = get_profile(db)
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
    from jobfinder.models import Job
    data = dict(source="Teste", title="Estágio Backend Python", company="ACME",
                description="Python e FastAPI. Envie currículo para vagas@acme.com", location="Remoto",
                modality="Remoto", job_type="Estágio", url=f"https://x.test/{os.urandom(4).hex()}",
                compatibility=80, level="estagio")
    data.update(kw)
    job = Job(**data)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
