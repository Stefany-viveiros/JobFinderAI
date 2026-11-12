import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from jobfinder import api as api_module
from jobfinder import applying
from tests.conftest import make_job


@pytest.fixture
def client(monkeypatch, test_user):
    # Exercita a API no modo SaaS real: sessão autenticada, CSRF e schema validado.
    monkeypatch.setenv("MULTITENANT_READY", "true")
    with TestClient(api_module.app, base_url="https://testserver") as c:
        login = c.post("/api/auth/login", json={
            "email": test_user.email, "password": "SenhaSegura123!"
        })
        assert login.status_code == 200
        session = c.get("/api/auth/me")
        assert session.status_code == 200
        c.headers.update({"X-CSRF-Token": session.json()["csrf_token"]})
        yield c


def test_backend_boots_and_core_routes_respond(client):
    assert client.get("/api/health").json()["status"] == "ok"
    for route in ("/api/dashboard", "/api/jobs", "/api/applications", "/api/tasks", "/api/profile",
                  "/api/attempts", "/api/agent/settings", "/api/sources", "/api/notifications"):
        assert client.get(route).status_code == 200, route


def test_dashboard_metrics_come_from_database(client, db, ready_profile):
    low = make_job(db, compatibility=30)
    high = make_job(db, compatibility=90)
    other = make_job(db, title="Senior Dev", level="outro", compatibility=95)
    assert client.post(f"/api/jobs/{high.id}/prepare").status_code == 200
    m = client.get("/api/dashboard").json()["metrics"]
    assert m["total_jobs"] == 3 and m["target_jobs"] == 2
    assert m["compatible_jobs"] == 1                                  # só alvo e >= 60
    assert (m["sent_applications"], m["pending_applications"], m["failed_applications"]) == (0, 1, 0)


def test_apply_endpoint_requires_explicit_confirmation(client, db):
    job = make_job(db)
    assert client.post(f"/api/jobs/{job.id}/apply", json={}).status_code == 400
    assert client.get("/api/dashboard").json()["metrics"]["sent_applications"] == 0
    ok = client.post(f"/api/jobs/{job.id}/apply", json={"confirmed": True})
    assert ok.status_code == 200
    m = client.get("/api/dashboard").json()["metrics"]
    assert m["sent_applications"] == 1 and m["sent_manually_confirmed"] == 1 and m["sent_automatically"] == 0
    assert client.post(f"/api/jobs/{job.id}/apply", json={"confirmed": True}).status_code == 409


def test_prepare_then_approve_flow_with_failure_then_success(client, db, ready_profile, smtp_on, monkeypatch):
    job = make_job(db)
    attempt = client.post(f"/api/jobs/{job.id}/prepare").json()["attempt"]
    assert attempt["status"] == "prepared" and "Python" in attempt["message"]
    monkeypatch.setattr(applying, "_deliver", lambda m: (_ for _ in ()).throw(OSError("falhou")))
    r = client.post(f"/api/attempts/{attempt['id']}/approve").json()
    assert r["attempt"]["status"] == "failed" and "falhou" in r["message"]
    assert client.get("/api/dashboard").json()["metrics"]["failed_applications"] == 1
    monkeypatch.setattr(applying, "_deliver", lambda m: smtp_on.append(m))
    r = client.post(f"/api/attempts/{attempt['id']}/approve").json()          # nova tentativa após falha
    assert r["attempt"]["status"] == "sent"
    assert client.post(f"/api/attempts/{attempt['id']}/cancel").status_code == 409


def test_job_filters(client, db):
    make_job(db, title="Estágio Python", source="Remotive", compatibility=80)
    make_job(db, title="Gerente Geral", source="Arbeitnow", level="outro", compatibility=20)
    titles = lambda qs: sorted(j["title"] for j in client.get("/api/jobs" + qs).json())
    assert titles("") == ["Estágio Python", "Gerente Geral"]
    assert titles("?level=alvo") == ["Estágio Python"]
    assert titles("?source=Arbeitnow") == ["Gerente Geral"]
    assert titles("?min_score=50") == ["Estágio Python"]
    assert titles("?q=gerente") == ["Gerente Geral"]
    assert titles("?attempt_status=sem_tentativa") == ["Estágio Python", "Gerente Geral"]


def test_manual_job_creation_and_duplicate_url(client):
    body = {"title": "Dev Jr", "url": "https://x.test/manual"}
    assert client.post("/api/jobs", json=body).json()["message"] == "Vaga salva ou atualizada no seu painel."
    assert client.post("/api/jobs", json=body).json()["message"] == "Link já cadastrado."


def test_collect_rejects_link_only_sources_and_reports_filters(client, monkeypatch):
    r = client.post("/api/jobs/collect", json={"sources": ["Indeed"]})
    assert r.status_code == 400 and "link" in r.json()["detail"].lower()
    items = [{"source": "Remotive", "title": "Estágio Dev Web", "company": "A", "url": "https://r.test/1", "description": "x"},
             {"source": "Remotive", "title": "Chef de Cozinha", "company": "B", "url": "https://r.test/2", "description": "y"}]
    monkeypatch.setattr(api_module, "collect_selected", lambda names: (items, ["Nerdin: Timeout"]))
    r = client.post("/api/jobs/collect", json={"sources": ["Remotive"]}).json()
    assert (r["saved"], r["filtered_out"], r["errors"]) == (1, 1, ["Nerdin: Timeout"])


def test_agent_settings_validation_and_persistence(client):
    assert client.put("/api/agent/settings", json={"daily_limit": 999}).status_code == 422
    r = client.put("/api/agent/settings", json={"auto_apply_enabled": True, "require_approval": False,
                                                 "daily_limit": 3, "min_score": 70}).json()
    assert r["settings"]["auto_apply_enabled"] and r["settings"]["daily_limit"] == 3
    assert client.get("/api/agent/settings").json()["min_score"] == 70


def test_sources_endpoint_flags_link_only_platforms(client):
    data = client.get("/api/sources").json()
    modes = {s["name"]: s["mode"] for s in data["sources"]}
    assert modes["Indeed"] == modes["Vagas.com"] == "link_only"
    assert all(not s["apply_api"] for s in data["sources"])
    assert data["external_links"]


def test_profile_supports_multiple_structured_records_and_updates(client):
    payload = {
        "educations": [
            {"course": "Engenharia da Computação", "institution": "FAM", "degree": "Bacharelado", "status": "Em andamento"},
            {"course": "Análise e Desenvolvimento de Sistemas", "institution": "Cruzeiro do Sul", "degree": "Tecnólogo", "status": "Em andamento"},
        ],
        "experiences": [
            {"company": "Empresa A", "role": "Cronoanalista", "start_date": "2018", "end_date": "2019", "description": "Análise de processos"}
        ],
        "courses": [{"name": "Desenvolvimento Web", "provider": "SENAI", "workload": "160 horas"}],
        "certifications_items": [{"name": "Cloud Fundamentals", "issuer": "Google"}],
        "portfolio_projects": [{"name": "JobFinder AI", "technologies": "Python, React"}],
    }
    saved = client.put("/api/profile", json=payload)
    assert saved.status_code == 200
    profile = client.get("/api/profile").json()
    assert len(profile["educations"]) == 2
    assert {item["course"] for item in profile["educations"]} == {
        "Engenharia da Computação", "Análise e Desenvolvimento de Sistemas"
    }
    assert profile["experiences"][0]["role"] == "Cronoanalista"
    assert profile["courses"][0]["workload"] == "160 horas"
    assert profile["certifications_items"][0]["issuer"] == "Google"
    assert profile["portfolio_projects"][0]["name"] == "JobFinder AI"

    first_education_id = profile["educations"][0]["id"]
    updated = client.put("/api/profile", json={
        "educations": [{"id": first_education_id, "course": "Engenharia da Computação", "institution": "FAM", "degree": "Bacharelado", "status": "Em andamento"}],
        "experiences": profile["experiences"],
        "courses": profile["courses"],
        "certifications_items": profile["certifications_items"],
        "portfolio_projects": profile["portfolio_projects"],
    })
    assert updated.status_code == 200
    assert len(client.get("/api/profile").json()["educations"]) == 1

    # Uma atualização parcial não deve apagar as coleções omitidas.
    partial = client.put("/api/profile", json={"technologies": "Python, React"})
    assert partial.status_code == 200
    after_partial = client.get("/api/profile").json()
    assert len(after_partial["educations"]) == 1
    assert after_partial["courses"][0]["name"] == "Desenvolvimento Web"


def test_profile_update_recomputes_scores(client, db):
    job = make_job(db, title="Estágio Python", description="Python", compatibility=0)
    client.put("/api/profile", json={"technologies": "Python", "interests": "Estágio"})
    assert client.get("/api/jobs").json()[0]["compatibility"] > 0


def test_approval_rejects_stale_or_unconfirmed_compatibility(client, db, ready_profile, test_user):
    from jobfinder.agent import get_agent_settings
    from jobfinder.models import JobMatch
    from sqlalchemy import select

    job = make_job(db, compatibility=55)
    attempt = client.post(f"/api/jobs/{job.id}/prepare").json()["attempt"]
    cfg = get_agent_settings(db, user_id=test_user.id)
    cfg.min_score = 60
    db.commit()
    response = client.post(f"/api/attempts/{attempt['id']}/approve")
    assert response.status_code == 409
    assert "abaixo do mínimo" in response.json()["detail"]

    match = db.scalar(select(JobMatch).where(
        JobMatch.user_id == test_user.id, JobMatch.job_id == job.id
    ))
    match.compatibility = 90
    match.missing_reasons = "Requisito(s) obrigatório(s) não identificado(s): java"
    db.commit()
    response = client.post(f"/api/attempts/{attempt['id']}/approve")
    assert response.status_code == 409
    assert "requisito(s) obrigatório(s)" in response.json()["detail"]


def test_login_rate_limit_returns_429_with_retry_after(client):
    payload = {"email": "unknown-rate-limit@example.com", "password": "SenhaIncorreta123!"}
    for _ in range(10):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401
    blocked = client.post("/api/auth/login", json=payload)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0



def test_rate_limit_cleanup_removes_expired_buckets(client, db):
    from datetime import datetime, timedelta
    from jobfinder.models import AuthRateLimit

    stale = AuthRateLimit(
        bucket_key="a" * 64,
        window_started_at=datetime.utcnow() - timedelta(days=3),
        attempts=999,
    )
    db.add(stale)
    db.commit()

    response = client.post("/api/auth/login", json={
        "email": "cleanup-check@example.com",
        "password": "SenhaIncorreta123!",
    })
    assert response.status_code == 401
    db.expire_all()
    assert db.get(AuthRateLimit, "a" * 64) is None

def test_market_analysis_is_rate_limited_per_account(client):
    first = client.post("/api/market/analysis/run", json={"level_scope": "both", "days": 30})
    assert first.status_code == 200
    second = client.post("/api/market/analysis/run", json={"level_scope": "both", "days": 30})
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0


def test_password_reset_invalidates_all_tokens_and_sessions(client, db, test_user):
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from jobfinder.models import PasswordResetToken, UserSession
    from jobfinder.api import _token_hash

    first_raw = "first-reset-token-value-long-enough"
    second_raw = "second-reset-token-value-long-enough"
    expires = datetime.utcnow() + timedelta(minutes=30)
    db.add_all([
        PasswordResetToken(user_id=test_user.id, token_hash=_token_hash(first_raw), expires_at=expires),
        PasswordResetToken(user_id=test_user.id, token_hash=_token_hash(second_raw), expires_at=expires),
    ])
    db.commit()

    response = client.post("/api/auth/reset-password", json={
        "token": first_raw,
        "password": "NovaSenhaSegura123!",
    })
    assert response.status_code == 200

    db.expire_all()
    tokens = db.scalars(select(PasswordResetToken).where(
        PasswordResetToken.user_id == test_user.id
    )).all()
    assert len(tokens) == 2
    assert all(token.used_at is not None for token in tokens)
    assert db.scalar(select(UserSession.id).where(
        UserSession.user_id == test_user.id
    )) is None

    # O link paralelo também deve ser recusado após a primeira troca.
    second = client.post("/api/auth/reset-password", json={
        "token": second_raw,
        "password": "OutraSenhaSegura456!",
    })
    assert second.status_code == 400
    assert client.get("/api/dashboard").status_code == 401


def test_two_accounts_cannot_read_or_modify_each_others_private_data(client, db, test_user):
    from jobfinder.models import User
    from jobfinder.api import password_hasher

    second_user = User(
        email="second@example.com",
        email_normalized="second@example.com",
        full_name="Segunda Conta",
        password_hash=password_hasher.hash("OutraSenhaSegura123!"),
        role="user",
        is_active=True,
    )
    db.add(second_user)
    db.commit()

    with TestClient(api_module.app, base_url="https://testserver") as second:
        login = second.post("/api/auth/login", json={
            "email": second_user.email,
            "password": "OutraSenhaSegura123!",
        })
        assert login.status_code == 200
        session = second.get("/api/auth/me")
        assert session.status_code == 200
        second.headers.update({"X-CSRF-Token": session.json()["csrf_token"]})

        # Perfil é privado por conta.
        assert client.put("/api/profile", json={"name": "Conta Primária"}).status_code == 200
        assert client.get("/api/profile").json()["name"] == "Conta Primária"
        assert second.get("/api/profile").json()["name"] != "Conta Primária"

        # Tarefas e candidaturas não podem ser lidas nem alteradas pela outra conta.
        task_response = client.post("/api/tasks", json={
            "title": "Tarefa privada da primeira conta",
            "description": "Não deve vazar",
            "priority": "Média",
            "notify": False,
        })
        assert task_response.status_code == 200
        task_id = task_response.json()["task"]["id"]
        assert second.get("/api/tasks").json() == []
        assert second.put(f"/api/tasks/{task_id}", json={
            "title": "Tentativa de alteração",
            "description": "",
            "due_date": None,
            "priority": "Média",
            "status": "Pendente",
            "notify": False,
        }).status_code == 404

        job = make_job(db)
        application_response = client.post(
            f"/api/jobs/{job.id}/apply", json={"confirmed": True}
        )
        assert application_response.status_code == 200
        application_id = application_response.json()["application_id"]
        assert second.get("/api/applications").json() == []
        assert second.put(f"/api/applications/{application_id}", json={
            "status": "Entrevista",
            "notes": "Alteração indevida",
            "recruiter": "",
            "deadline": None,
        }).status_code == 404

        assert second.get("/api/attempts").json() == []

        # Preferências do agente também são individuais.
        settings_response = client.put("/api/agent/settings", json={
            "auto_apply_enabled": True,
            "require_approval": False,
            "daily_limit": 12,
            "min_score": 91,
        })
        assert settings_response.status_code == 200
        assert client.get("/api/agent/settings").json()["daily_limit"] == 12
        assert second.get("/api/agent/settings").json()["daily_limit"] != 12
        assert second.get("/api/agent/settings").json()["min_score"] == 80

        # Plano de desenvolvimento e avaliações pertencem à conta que os criou.
        from jobfinder.models import Skill, NotificationLog
        skill = Skill(
            canonical_name="Python",
            category="language",
            aliases_json='["py"]',
            active=True,
            taxonomy_version="test",
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)

        plan_response = client.post("/api/market/development-plan", json={
            "skill_id": skill.id,
            "title": "Projeto privado de Python",
            "objective": "Praticar programação",
            "activity": "Construir uma API",
            "estimated_hours": 8,
        })
        assert plan_response.status_code == 200
        plan_item_id = plan_response.json()["item"]["id"]
        assert second.get("/api/market/development-plan").json()["items"] == []
        assert second.patch(f"/api/market/development-plan/{plan_item_id}", json={
            "status": "completed",
        }).status_code == 404

        assessment_response = client.post("/api/market/assessments", json={
            "skill_id": skill.id,
            "plan_item_id": plan_item_id,
        })
        assert assessment_response.status_code == 200
        assessment_id = assessment_response.json()["attempt"]["id"]
        assert second.get("/api/market/assessments").json()["attempts"] == []
        assert second.post(f"/api/market/assessments/{assessment_id}/submit", json={
            "response_text": "Tentativa de acessar avaliação de outra conta.",
            "evidence_url": "",
            "rubric_answers": {},
        }).status_code == 404

        db.add(NotificationLog(
            user_id=test_user.id,
            task_id=None,
            recipient="primary@example.com",
            send_date="2026-11-02",
            status="sent",
            detail="notificação privada",
        ))
        db.commit()
        assert second.get("/api/notifications").json() == []

def test_career_twin_returns_traceable_profile_evidence(client, db, ready_profile):
    from datetime import datetime
    from jobfinder.models import PortfolioProject, Skill, SkillAssessmentAttempt, DevelopmentPlanItem

    project = PortfolioProject(
        profile_id=ready_profile.id,
        name="API de portfólio",
        description="Serviço backend construído com Python e FastAPI.",
        technologies="Python, FastAPI, PostgreSQL",
        status="Concluído",
        repository_url="https://github.com/example/api",
    )
    db.add(project)

    sql = Skill(
        canonical_name="SQL",
        category="database",
        aliases_json='["sql"]',
        active=True,
        taxonomy_version="test",
    )
    db.add(sql)
    db.flush()
    plan_item = DevelopmentPlanItem(
        user_id=ready_profile.user_id,
        skill_id=sql.id,
        title="Concluir prática de SQL",
        objective="Construir uma consulta com JOIN e agregação.",
        activity="Criar e documentar consulta.",
        estimated_hours=4,
        status="completed",
        progress_percent=100,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db.add(plan_item)
    db.flush()
    db.add(SkillAssessmentAttempt(
        user_id=ready_profile.user_id,
        skill_id=sql.id,
        plan_item_id=plan_item.id,
        challenge_title="Desafio SQL",
        challenge_prompt="Consulta com JOIN e agregação",
        rubric_json="[]",
        response_text="Escrevi uma consulta SQL com JOIN e GROUP BY para consolidar os resultados.",
        evidence_url="",
        rubric_answers_json="{}",
        score=75,
        feedback="Autoavaliação registrada.",
        status="self_reviewed",
        submitted_at=datetime.utcnow(),
    ))
    db.commit()

    response = client.get("/api/career-twin")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["profile"]["name"] == "Ana Teste"
    assert payload["summary"]["skills_identified"] >= 3

    python_skill = next(item for item in payload["skills"] if item["name"] == "Python")
    assert python_skill["status"] == "completed_project"
    assert any(item["source_type"] == "completed_project" for item in python_skill["evidence"])
    assert any(item["source_type"] == "self_declared" for item in python_skill["evidence"])

    sql_skill = next(item for item in payload["skills"] if item["name"] == "SQL")
    assert sql_skill["status"] == "self_assessed"
    assert sql_skill["self_assessment"]["result_kind"] == "self_assessment"
    assert sql_skill["self_assessment"]["plan_item_id"] == plan_item.id
    assert "não é validação independente" in sql_skill["self_assessment"]["notice"]

    timeline = payload["timeline"]
    assert any(item["event_type"] == "development_goal_completed" for item in timeline)
    challenge_event = next(item for item in timeline if item["event_type"] == "self_assessment_submitted")
    assert challenge_event["status"] == "self_reviewed"
    assert "Não representa validação independente" in challenge_event["detail"]
    assert f"Meta vinculada: #{plan_item.id}" in challenge_event["detail"]


def test_career_twin_is_isolated_between_accounts(client, db, test_user, ready_profile):
    from fastapi.testclient import TestClient
    from jobfinder.models import User
    from jobfinder.api import password_hasher
    from jobfinder.service import get_profile

    second_user = User(
        email="career-twin-second@example.com",
        email_normalized="career-twin-second@example.com",
        full_name="Segunda Pessoa",
        password_hash=password_hasher.hash("OutraSenhaSegura123!"),
        role="user",
        is_active=True,
    )
    db.add(second_user)
    db.commit()
    second_profile = get_profile(db, user_id=second_user.id)
    second_profile.name = "Segunda Pessoa"
    second_profile.technologies = "React e TypeScript"
    db.commit()

    first_payload = client.get("/api/career-twin").json()
    assert first_payload["profile"]["name"] == "Ana Teste"
    assert "React" not in {item["name"] for item in first_payload["skills"]}

    with TestClient(api_module.app, base_url="https://testserver") as second:
        login = second.post("/api/auth/login", json={
            "email": second_user.email,
            "password": "OutraSenhaSegura123!",
        })
        assert login.status_code == 200
        session = second.get("/api/auth/me")
        assert session.status_code == 200
        second.headers.update({"X-CSRF-Token": session.json()["csrf_token"]})
        second_payload = second.get("/api/career-twin").json()

    assert second_payload["profile"]["name"] == "Segunda Pessoa"
    assert "React" in {item["name"] for item in second_payload["skills"]}
    assert "Python" not in {item["name"] for item in second_payload["skills"]}



def _build_docx_resume():
    document = Document()
    document.add_paragraph("Pessoa de Teste")
    document.add_paragraph("Desenvolvimento de software com Python, FastAPI e SQL.")
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _post_resume_import(client, *, allow_external_ai=None, content=None):
    data = {}
    if allow_external_ai is not None:
        data["allow_external_ai"] = str(allow_external_ai).lower()
    return client.post(
        "/api/profile/import",
        files={
            "file": (
                "curriculo.docx",
                content if content is not None else _build_docx_resume(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data=data,
    )


def test_resume_import_requires_explicit_consent_before_calling_gemini(client, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(api_module, "settings", SimpleNamespace(gemini_api_key="chave-de-teste"))
    gemini_calls = []
    monkeypatch.setattr(
        api_module, "analyze_resume_with_gemini",
        lambda text: gemini_calls.append(text) or {"name": "Pessoa analisada"},
    )
    monkeypatch.setattr(
        api_module, "parse_resume",
        lambda content, filename: {"name": "Pessoa extraída localmente"},
    )

    local = _post_resume_import(client)
    assert local.status_code == 200
    assert local.json()["analysis_mode"] == "basic"
    assert local.json()["extracted"]["name"] == "Pessoa extraída localmente"
    assert gemini_calls == []

    external = _post_resume_import(client, allow_external_ai=True)
    assert external.status_code == 200
    assert external.json()["analysis_mode"] == "gemini"
    assert gemini_calls == ["Pessoa de Teste\nDesenvolvimento de software com Python, FastAPI e SQL."]


def test_resume_import_rejects_content_that_does_not_match_docx_extension(client):
    response = _post_resume_import(client, content=b"isto nao e um arquivo DOCX")
    assert response.status_code == 400
    assert "DOCX válido" in response.json()["detail"]


def test_resume_import_has_per_account_rate_limit(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "extract_resume_text",
        lambda content, filename: "Texto de currículo suficiente para análise.",
    )
    monkeypatch.setattr(
        api_module, "parse_resume",
        lambda content, filename: {"name": "Pessoa de Teste"},
    )

    for _ in range(5):
        response = _post_resume_import(client)
        assert response.status_code == 200

    blocked = _post_resume_import(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_attempt_actions_are_isolated_between_accounts(client, db, test_user):
    from fastapi.testclient import TestClient
    from jobfinder.api import password_hasher
    from jobfinder.models import ApplicationAttempt, User

    second_user = User(
        email="attempt-isolation@example.com",
        email_normalized="attempt-isolation@example.com",
        full_name="Conta Secundária",
        password_hash=password_hasher.hash("SenhaSeguraDaSegundaConta123!"),
        role="user",
        is_active=True,
    )
    db.add(second_user)
    db.commit()

    job = make_job(db)
    attempts = [
        ApplicationAttempt(
            user_id=test_user.id, job_id=job.id, status="prepared", channel="email",
            recipient="recrutamento@example.test", subject="Candidatura de teste",
            message="Mensagem privada da primeira conta.",
        ),
        ApplicationAttempt(
            user_id=test_user.id, job_id=job.id, status="prepared", channel="email",
            recipient="recrutamento@example.test", subject="Outra candidatura de teste",
            message="Outra mensagem privada da primeira conta.",
        ),
    ]
    db.add_all(attempts)
    db.commit()
    cancel_id, approve_id = attempts[0].id, attempts[1].id

    with TestClient(api_module.app, base_url="https://testserver") as second:
        login = second.post("/api/auth/login", json={
            "email": second_user.email,
            "password": "SenhaSeguraDaSegundaConta123!",
        })
        assert login.status_code == 200
        session = second.get("/api/auth/me")
        assert session.status_code == 200
        second.headers.update({"X-CSRF-Token": session.json()["csrf_token"]})

        assert second.get("/api/attempts").json() == []
        assert second.post(f"/api/attempts/{cancel_id}/cancel").status_code == 404
        assert second.post(f"/api/attempts/{approve_id}/approve").status_code == 404

    own_attempts = {item["id"]: item for item in client.get("/api/attempts").json()}
    assert own_attempts[cancel_id]["status"] == "prepared"
    assert own_attempts[approve_id]["status"] == "prepared"


def test_workspace_remains_fail_closed_when_multitenant_gate_is_disabled(client, monkeypatch):
    monkeypatch.setenv("MULTITENANT_READY", "false")
    assert client.get("/api/dashboard").status_code == 503
    assert client.get("/api/profile").status_code == 503
    assert client.post("/api/tasks", json={
        "title": "Não deve ser criada",
        "notify": False,
    }).status_code == 503


def test_authenticated_writes_require_csrf_token(client):
    client.headers.pop("X-CSRF-Token", None)
    response = client.put("/api/agent/settings", json={
        "auto_apply_enabled": False,
        "require_approval": True,
        "daily_limit": 5,
        "min_score": 80,
    })
    assert response.status_code == 403



def test_job_diagnosis_is_scoped_to_the_authenticated_users_job_list(client, db, test_user, ready_profile):
    from fastapi.testclient import TestClient
    from jobfinder.api import password_hasher
    from jobfinder.models import User

    job = make_job(
        db,
        description="Python é obrigatório. React é desejável.",
        compatibility=82,
    )
    primary = client.get(f"/api/jobs/{job.id}/diagnosis")
    assert primary.status_code == 200
    payload = primary.json()
    assert payload["compatibility"]["score"] == 82
    assert payload["compatibility"]["label"].startswith("Triagem heurística")
    by_name = {item["name"]: item for item in payload["requirements"]}
    assert by_name["python"]["requirement_type"] == "mandatory"
    assert by_name["react"]["requirement_type"] == "desirable"

    second_user = User(
        email="job-diagnosis-other@example.com",
        email_normalized="job-diagnosis-other@example.com",
        full_name="Outra Conta",
        password_hash=password_hasher.hash("SenhaSeguraOutraConta123!"),
        role="user",
        is_active=True,
    )
    db.add(second_user)
    db.commit()

    with TestClient(api_module.app, base_url="https://testserver") as second:
        login = second.post("/api/auth/login", json={
            "email": second_user.email,
            "password": "SenhaSeguraOutraConta123!",
        })
        assert login.status_code == 200
        session = second.get("/api/auth/me")
        second.headers.update({"X-CSRF-Token": session.json()["csrf_token"]})
        assert second.get(f"/api/jobs/{job.id}/diagnosis").status_code == 404



def test_application_status_history_records_manual_and_initial_transitions(client, db):
    job = make_job(db)
    sent = client.post(f"/api/jobs/{job.id}/apply", json={"confirmed": True})
    assert sent.status_code == 200
    application_id = sent.json()["application_id"]

    initial = client.get(f"/api/applications/{application_id}/history")
    assert initial.status_code == 200
    assert initial.json()["has_history"] is True
    assert len(initial.json()["events"]) == 1
    first = initial.json()["events"][0]
    assert first["previous_status"] == ""
    assert first["new_status"] == "Candidatura enviada"
    assert first["source"] == "manual_confirmed"

    updated = client.put(f"/api/applications/{application_id}", json={
        "status": "Entrevista",
        "applied_at": "2026-11-12",
        "deadline": None,
        "recruiter": "Pessoa recrutadora",
        "notes": "Entrevista técnica agendada.",
    })
    assert updated.status_code == 200
    history = client.get(f"/api/applications/{application_id}/history").json()
    assert len(history["events"]) == 2
    last = history["events"][1]
    assert last["previous_status"] == "Candidatura enviada"
    assert last["new_status"] == "Entrevista"
    assert last["source"] == "manual"
    assert last["note"] == "Entrevista técnica agendada."
    assert "não são inferidas retroativamente" in history["notice"]

    # Salvar observações sem alterar a etapa não cria eventos duplicados.
    unchanged = client.put(f"/api/applications/{application_id}", json={
        "status": "Entrevista",
        "applied_at": "2026-11-12",
        "deadline": None,
        "recruiter": "Pessoa recrutadora",
        "notes": "Atualizei as observações.",
    })
    assert unchanged.status_code == 200
    final = client.get(f"/api/applications/{application_id}/history").json()
    assert len(final["events"]) == 2


def test_application_history_is_isolated_between_accounts(client, db, test_user):
    from fastapi.testclient import TestClient
    from jobfinder.api import password_hasher
    from jobfinder.models import User

    job = make_job(db)
    response = client.post(f"/api/jobs/{job.id}/apply", json={"confirmed": True})
    application_id = response.json()["application_id"]

    second_user = User(
        email="application-history-other@example.com",
        email_normalized="application-history-other@example.com",
        full_name="Outra Conta",
        password_hash=password_hasher.hash("SenhaSeguraOutraConta123!"),
        role="user",
        is_active=True,
    )
    db.add(second_user)
    db.commit()

    with TestClient(api_module.app, base_url="https://testserver") as second:
        login = second.post("/api/auth/login", json={
            "email": second_user.email,
            "password": "SenhaSeguraOutraConta123!",
        })
        assert login.status_code == 200
        session = second.get("/api/auth/me")
        assert session.status_code == 200
        second.headers.update({"X-CSRF-Token": session.json()["csrf_token"]})
        assert second.get(f"/api/applications/{application_id}/history").status_code == 404



def test_attempt_list_uses_private_job_match_not_legacy_global_job_score(client, db, test_user):
    from fastapi.testclient import TestClient
    from jobfinder.api import password_hasher
    from jobfinder.models import ApplicationAttempt, JobMatch, User
    from sqlalchemy import select

    job = make_job(db, compatibility=99)
    primary_match = db.scalar(select(JobMatch).where(
        JobMatch.user_id == test_user.id,
        JobMatch.job_id == job.id,
    ))
    primary_match.compatibility = 83
    primary_match.missing_reasons = "Lacuna privada da primeira conta"

    # Simula legado: estes campos já não são a fonte de score para contas.
    job.compatibility = 99
    job.missing_reasons = "LEGADO GLOBAL NAO DEVE SER EXIBIDO"

    second_user = User(
        email="attempt-list-second@example.com",
        email_normalized="attempt-list-second@example.com",
        full_name="Segunda Conta",
        password_hash=password_hasher.hash("SenhaSeguraOutraConta123!"),
        role="user",
        is_active=True,
    )
    db.add(second_user)
    db.flush()
    db.add(JobMatch(
        user_id=second_user.id,
        job_id=job.id,
        compatibility=21,
        match_reasons="Apenas segunda conta",
        missing_reasons="Lacuna privada da segunda conta",
    ))
    db.add_all([
        ApplicationAttempt(
            user_id=test_user.id,
            job_id=job.id,
            status="prepared",
            channel="manual",
            message="Texto da primeira conta",
        ),
        ApplicationAttempt(
            user_id=second_user.id,
            job_id=job.id,
            status="prepared",
            channel="manual",
            message="Texto da segunda conta",
        ),
    ])
    db.commit()

    primary = client.get("/api/attempts").json()
    assert len(primary) == 1
    assert primary[0]["job"]["compatibility"] == 83
    assert primary[0]["job"]["missing_reasons"] == "Lacuna privada da primeira conta"
    assert "LEGADO GLOBAL" not in primary[0]["job"]["missing_reasons"]

    with TestClient(api_module.app, base_url="https://testserver") as second:
        login = second.post("/api/auth/login", json={
            "email": second_user.email,
            "password": "SenhaSeguraOutraConta123!",
        })
        assert login.status_code == 200
        session = second.get("/api/auth/me")
        assert session.status_code == 200
        second.headers.update({"X-CSRF-Token": session.json()["csrf_token"]})

        secondary = second.get("/api/attempts").json()
        assert len(secondary) == 1
        assert secondary[0]["job"]["compatibility"] == 21
        assert secondary[0]["job"]["missing_reasons"] == "Lacuna privada da segunda conta"
        assert secondary[0]["job"]["missing_reasons"] != primary[0]["job"]["missing_reasons"]


def test_account_rate_limit_is_shared_across_client_ips(db):
    from fastapi import HTTPException, Request
    from jobfinder.api import _enforce_rate_limit

    def request_from(ip):
        return Request({
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/profile/import",
            "raw_path": b"/api/profile/import",
            "query_string": b"",
            "headers": [],
            "client": (ip, 54321),
            "server": ("jobfinder.test", 443),
        })

    # O mesmo usuário não ganha uma nova cota ao trocar de IP.
    _enforce_rate_limit(
        db, request_from("203.0.113.10"),
        scope="resume-import-user", subject="user-42",
        limit=1, window_seconds=3600,
    )
    with pytest.raises(HTTPException) as blocked:
        _enforce_rate_limit(
            db, request_from("198.51.100.20"),
            scope="resume-import-user", subject="user-42",
            limit=1, window_seconds=3600,
        )
    assert blocked.value.status_code == 429

    # A conta diferente mantém sua própria janela, mesmo que a origem coincida.
    _enforce_rate_limit(
        db, request_from("203.0.113.10"),
        scope="resume-import-user", subject="user-43",
        limit=1, window_seconds=3600,
    )


def test_job_actions_require_opportunity_linked_to_authenticated_account(client, db, test_user):
    from jobfinder.models import Job, JobMatch, User
    from jobfinder.api import password_hasher

    other_user = User(
        email="job-owner@example.com",
        email_normalized="job-owner@example.com",
        full_name="Pessoa proprietária da vaga",
        password_hash=password_hasher.hash("SenhaDaOutraConta123!"),
        role="user",
        is_active=True,
    )
    db.add(other_user)
    db.flush()
    foreign_job = Job(
        source="Teste",
        title="Vaga privada de outra conta",
        company="Empresa externa",
        description="Descrição da vaga",
        location="Remoto",
        modality="Remoto",
        job_type="Estágio",
        url="https://foreign-job.test/private-opportunity",
        compatibility=95,
        level="estagio",
    )
    db.add(foreign_job)
    db.flush()
    db.add(JobMatch(
        user_id=other_user.id,
        job_id=foreign_job.id,
        compatibility=95,
        is_archived=False,
    ))
    db.commit()

    # Conhecer um ID global não concede acesso à oportunidade de outra conta.
    assert client.post("/api/tasks", json={
        "title": "Tarefa vinculada indevidamente",
        "job_id": foreign_job.id,
        "notify": False,
    }).status_code == 404
    assert client.patch(f"/api/jobs/{foreign_job.id}/favorite").status_code == 404
    assert client.post(f"/api/jobs/{foreign_job.id}/apply", json={
        "confirmed": True,
    }).status_code == 404
    assert client.post(f"/api/jobs/{foreign_job.id}/prepare").status_code == 404

    # Nenhuma operação negada deve criar dados privados para a conta atacante.
    assert client.get("/api/tasks").json() == []
    assert client.get("/api/applications").json() == []
    assert client.get("/api/attempts").json() == []


def test_multitenant_schema_validator_fails_closed_on_legacy_unowned_rows(db):
    from jobfinder.db import validate_multitenant_schema
    from jobfinder.models import Task

    # Um schema recém-criado deve satisfazer as FKs e constraints necessárias.
    validate_multitenant_schema()

    legacy_task = Task(
        user_id=None,
        title="Tarefa legada sem proprietário",
        description="Não pode ser exposta a uma conta nova.",
        notify=False,
    )
    db.add(legacy_task)
    db.commit()

    with pytest.raises(RuntimeError, match="sem proprietário"):
        validate_multitenant_schema()

    db.delete(legacy_task)
    db.commit()
    validate_multitenant_schema()
