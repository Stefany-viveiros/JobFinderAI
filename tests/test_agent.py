from jobfinder import applying
from jobfinder.agent import get_agent_settings, run_agent
from jobfinder.models import ApplicationAttempt
from sqlalchemy import select


def feed(*extra):
    items = [
        {"source": "Remotive", "title": "Estágio Backend Python", "company": "ACME", "url": "https://a.test/1",
         "description": "Python FastAPI. Envie para vagas@acme.com", "location": "Brasil", "modality": "Remoto", "job_type": "Estágio"},
        {"source": "OkEmprego", "title": "Estagio  Backend Python", "company": "ACME Ltda", "url": "https://b.test/9",
         "description": "mesma vaga em outra fonte", "location": "Brasil", "modality": "Remoto", "job_type": "Estágio"},
        {"source": "Remotive", "title": "Senior Python Developer", "company": "Big", "url": "https://a.test/2",
         "description": "Python", "location": "Remote", "modality": "Remoto", "job_type": "full_time"},
        {"source": "Nerdin", "title": "Desenvolvedor Júnior Backend Python", "company": "Beta", "url": "https://a.test/3",
         "description": "Python FastAPI Git APIs REST, estágio. Sem e-mail de contato", "location": "Brasil", "modality": "Remoto", "job_type": "Júnior"},
    ]
    return lambda names: (items + list(extra), [])


def statuses(db):
    return sorted((a.status, a.channel) for a in db.scalars(select(ApplicationAttempt)).all())


def test_pipeline_filters_dedupes_and_prepares_with_approval(db, ready_profile, smtp_on):
    result = run_agent(db, collector=feed())
    assert result["received"] == 4 and result["saved"] == 2      # sênior filtrado; "ACME Ltda" = "ACME" entre fontes
    assert result["filtered_out"] == 1
    assert result["awaiting_approval"] == 1 and result["manual_required"] == 1
    assert statuses(db) == [("awaiting_approval", "email"), ("manual_required", "manual")]
    assert smtp_on == []                                         # nada enviado sem aprovação
    again = run_agent(db, collector=feed())                      # segunda rodada não duplica nada
    assert again["saved"] == 0 and again["duplicates"] >= 3 and len(statuses(db)) == 2


def test_auto_send_respects_toggle_and_daily_limit(db, ready_profile, smtp_on):
    cfg = get_agent_settings(db)
    cfg.require_approval, cfg.auto_apply_enabled, cfg.daily_limit = False, False, 1
    db.commit()
    extra = {"source": "Remotive", "title": "Estágio Dados Python", "company": "Gama", "url": "https://a.test/4",
             "description": "Python. rh@gama.com", "location": "Brasil", "modality": "Remoto", "job_type": "Estágio"}
    r = run_agent(db, collector=feed(extra))
    assert r["sent"] == 0 and smtp_on == []                       # envio automático desativado
    assert r["prepared"] == 2

    cfg = get_agent_settings(db)
    cfg.auto_apply_enabled = True
    db.commit()
    for a in db.scalars(select(ApplicationAttempt)).all():
        db.delete(a)
    db.commit()
    r = run_agent(db, collector=feed(extra), collect=False)
    assert r["sent"] == 1 and r["skipped_daily_limit"] == 1 and len(smtp_on) == 1
    assert applying.sent_today_count(db) == 1


def test_incomplete_profile_collects_but_prepares_nothing(db):
    r = run_agent(db, collector=feed())
    assert r["saved"] == 2 and r["profile_gaps"] and "perfil" in r["message"]
    assert db.scalars(select(ApplicationAttempt)).all() == []


def test_smtp_failure_is_recorded_as_failed(db, ready_profile, smtp_on, monkeypatch):
    cfg = get_agent_settings(db)
    cfg.require_approval, cfg.auto_apply_enabled = False, True
    db.commit()
    monkeypatch.setattr(applying, "_deliver", lambda m: (_ for _ in ()).throw(OSError("sem rede")))
    r = run_agent(db, collector=feed())
    assert r["failed"] == 1 and r["sent"] == 0
    assert ("failed", "email") in statuses(db)


def test_jobs_below_min_score_are_not_prepared(db, ready_profile):
    weak = {"source": "Nerdin", "title": "Estágio Mobile Android", "company": "Fraca", "url": "https://a.test/9",
            "description": "Kotlin", "location": "Portugal", "modality": "Presencial", "job_type": "Estágio"}
    r = run_agent(db, collector=lambda names: ([weak], []))
    assert r["saved"] == 1 and r["candidates"] == 0
    assert db.scalars(select(ApplicationAttempt)).all() == []


def test_agent_does_not_prepare_job_with_unconfirmed_mandatory_technology(db, ready_profile):
    cfg = get_agent_settings(db)
    cfg.min_score = 0
    db.commit()
    item = {
        "source": "Nerdin",
        "title": "Estágio Backend Python",
        "company": "Obrigatória",
        "url": "https://a.test/mandatory",
        "description": "Requisito obrigatório: Java. Python é desejável.",
        "location": "Brasil",
        "modality": "Remoto",
        "job_type": "Estágio",
    }
    result = run_agent(db, collector=lambda names: ([item], []))
    assert result["saved"] == 1
    assert result["candidates"] == 0
    assert db.scalars(select(ApplicationAttempt)).all() == []
