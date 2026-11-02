import pytest
from fastapi.testclient import TestClient

from jobfinder import api as api_module
from jobfinder import applying
from tests.conftest import make_job


@pytest.fixture
def client(monkeypatch, test_user):
    # Exercita a API no modo SaaS real: sessão autenticada, CSRF e schema validado.
    monkeypatch.setenv("MULTITENANT_READY", "true")
    with TestClient(api_module.app) as c:
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
    assert client.post("/api/jobs", json=body).json()["message"] == "Vaga salva com sucesso."
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

    job = make_job(db, compatibility=55)
    attempt = client.post(f"/api/jobs/{job.id}/prepare").json()["attempt"]
    cfg = get_agent_settings(db, user_id=test_user.id)
    cfg.min_score = 60
    db.commit()
    response = client.post(f"/api/attempts/{attempt['id']}/approve")
    assert response.status_code == 409
    assert "abaixo do mínimo" in response.json()["detail"]

    job.compatibility = 90
    job.missing_reasons = "Requisito(s) obrigatório(s) não identificado(s): java"
    db.commit()
    response = client.post(f"/api/attempts/{attempt['id']}/approve")
    assert response.status_code == 409
    assert "requisito(s) obrigatório(s)" in response.json()["detail"]
