from datetime import datetime
import uuid

from sqlalchemy import select

from jobfinder.market_service import (
    create_market_snapshot,
    index_job_skills,
    index_unprocessed_jobs,
)
from jobfinder.models import JobSkill, MarketSkillMetric, MarketSkillPair, Skill
from jobfinder.models import Job


def make_job(db, **overrides):
    data = {
        "source": "Teste", "title": "Estágio Backend Python",
        "company": "Empresa teste", "description": "Python e FastAPI são utilizados no backend.",
        "location": "Brasil", "modality": "Remoto", "job_type": "Estágio",
        "url": f"https://test.local/{uuid.uuid4()}", "level": "estagio",
        "created_at": datetime.utcnow(),
    }
    data.update(overrides)
    job = Job(**data)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_index_job_skills_persists_one_row_per_canonical_skill(db):
    job = make_job(
        db,
        title="Estágio JavaScript",
        description="JS e JavaScript são usados no frontend. Também usamos React.",
    )

    count = index_job_skills(db, job)
    rows = db.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all()
    names = {
        db.get(Skill, row.skill_id).canonical_name
        for row in rows
    }

    assert count == 2
    assert names == {"JavaScript", "React"}
    assert len(rows) == 2


def test_index_job_skills_is_idempotent(db):
    job = make_job(db, title="Estágio Python", description="Python, FastAPI e SQL.")
    first = index_job_skills(db, job)
    second = index_job_skills(db, job)
    rows = db.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all()

    assert first == second == 3
    assert len(rows) == 3


def test_market_snapshot_counts_distinct_jobs_and_pairs(db):
    make_job(db, title="Estágio Python", description="Python, FastAPI e SQL.")
    make_job(
        db,
        title="Pessoa Desenvolvedora Júnior",
        job_type="Júnior",
        level="junior",
        description="Python e FastAPI são desejáveis.",
    )
    # Fora do público-alvo: não entra no snapshot.
    make_job(db, title="Desenvolvedor Pleno Python", level="outro")

    result = create_market_snapshot(db, level_scope="both", days=30, min_jobs=2)

    assert result["total_jobs"] == 2
    assert result["sample_sufficient"] is True
    metrics = db.scalars(
        select(MarketSkillMetric).where(MarketSkillMetric.run_id == result["run_id"])
    ).all()
    pairs = db.scalars(
        select(MarketSkillPair).where(MarketSkillPair.run_id == result["run_id"])
    ).all()

    python = next(
        row for row in metrics
        if db.get(Skill, row.skill_id).canonical_name == "Python"
    )
    assert python.jobs_count == 2
    assert python.mention_rate == 1.0
    assert any(
        {db.get(Skill, row.skill_a_id).canonical_name,
         db.get(Skill, row.skill_b_id).canonical_name} == {"Python", "FastAPI"}
        for row in pairs
    )


def test_market_snapshot_marks_small_sample_as_insufficient(db):
    make_job(db, title="Estágio Python", description="Python para backend.")

    result = create_market_snapshot(db, level_scope="estagio", days=30, min_jobs=30)

    assert result["total_jobs"] == 1
    assert result["sample_sufficient"] is False
    assert "Amostra insuficiente" in result["quality_notes"]


def test_index_unprocessed_jobs_does_not_reindex_existing_evidence(db):
    make_job(db, title="Estágio React", description="React e JavaScript.")
    first = index_unprocessed_jobs(db)
    second = index_unprocessed_jobs(db)

    assert first["jobs_indexed"] == 1
    assert second["jobs_indexed"] == 0


def test_empty_extraction_is_recorded_and_not_repeated(db):
    make_job(
        db,
        title="Estágio em tecnologia",
        description="Boa comunicação, organização e vontade de aprender.",
    )
    first = index_unprocessed_jobs(db)
    second = index_unprocessed_jobs(db)

    assert first["jobs_indexed"] == 1
    assert second["jobs_indexed"] == 0


def test_profile_gap_distinguishes_project_course_declaration_and_missing(db, test_user):
    from jobfinder.market_service import build_profile_gap
    from jobfinder.models import Profile, PortfolioProject, Course

    profile = Profile(
        user_id=test_user.id,
        technologies="JavaScript",
        skills="",
        keywords="",
        portfolio_projects=[
            PortfolioProject(
                name="Projeto de portfólio",
                description="Aplicação web com React.",
                technologies="React",
                status="Concluído",
            )
        ],
        courses=[
            Course(name="Python básico", provider="Curso teste", status="Concluído")
        ],
    )
    db.add(profile)
    db.commit()

    make_job(
        db,
        title="Estágio Frontend Python",
        description="Python, React, JavaScript e Docker são competências desejáveis para esta vaga.",
    )
    snapshot = create_market_snapshot(db, level_scope="estagio", days=30, min_jobs=1)
    gap = build_profile_gap(db, user_id=test_user.id, run_id=snapshot["run_id"])
    by_name = {item["name"]: item for item in gap["items"]}

    assert by_name["React"]["status"] == "praticada"
    assert by_name["Python"]["status"] == "curso_concluido"
    assert by_name["JavaScript"]["status"] == "declarada"
    assert by_name["Docker"]["status"] == "nao_identificada"
    assert gap["available"] is True
    assert "não significa falta de conhecimento" in gap["notice"]


def test_development_plan_creates_tracks_and_summarizes_goal(db, test_user):
    from jobfinder.market_service import (
        create_development_item, list_development_plan, update_development_item,
    )
    skill = Skill(canonical_name="Docker", category="Infraestrutura", aliases_json="[]", active=True)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    item = create_development_item(db, user_id=test_user.id, skill_id=skill.id, estimated_hours=6)
    assert item["status"] == "planned"
    assert item["progress_percent"] == 0
    assert item["estimated_hours"] == 6
    assert "Docker" in item["activity"]

    updated = update_development_item(db, item["id"], {
        "status": "in_progress", "progress_percent": 50, "notes": "Estudei imagens e containers."
    }, user_id=test_user.id)
    assert updated["status"] == "in_progress"
    assert updated["progress_percent"] == 50

    completed = update_development_item(db, item["id"], {"status": "completed"}, user_id=test_user.id)
    assert completed["progress_percent"] == 100
    assert completed["completed_at"] is not None

    plan = list_development_plan(db, user_id=test_user.id)
    assert plan["summary"]["total"] == 1
    assert plan["summary"]["completed"] == 1
    assert plan["summary"]["completion_rate"] == 100.0


def test_development_plan_prevents_duplicate_active_goal_for_same_skill(db, test_user):
    from jobfinder.market_service import create_development_item
    skill = Skill(canonical_name="FastAPI", category="Framework", aliases_json="[]", active=True)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    create_development_item(db, user_id=test_user.id, skill_id=skill.id)
    try:
        create_development_item(db, skill_id=skill.id)
        assert False, "Era esperado impedir uma meta ativa duplicada."
    except ValueError as exc:
        assert "Já existe uma meta ativa" in str(exc)


def test_skill_assessment_generates_challenge_and_records_self_review(db, test_user):
    from jobfinder.market_service import (
        create_skill_assessment, submit_skill_assessment, list_skill_assessments,
    )
    skill = Skill(canonical_name="Python", category="language", aliases_json="[]", active=True)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    attempt = create_skill_assessment(db, user_id=test_user.id, skill_id=skill.id)
    assert attempt["status"] == "draft"
    assert "Python" in attempt["title"]
    assert len(attempt["criteria"]) == 4
    assert attempt["notice"].startswith("Resultado de autoavaliação")

    answers = {criterion["id"]: True for criterion in attempt["criteria"]}
    submitted = submit_skill_assessment(
        db,
        attempt["id"],
        response_text="Implementei uma pequena aplicação, tratei entradas e documentei como executar.",
        evidence_url="https://github.com/example/python-challenge",
        rubric_answers=answers,
    )
    assert submitted["status"] == "self_reviewed"
    assert submitted["score"] == 100
    assert "autoavaliação" in submitted["result_kind"]
    assert "Não é uma certificação" in submitted["notice"]

    history = list_skill_assessments(db, user_id=test_user.id)
    assert history["summary"]["total"] == 1
    assert history["summary"]["submitted"] == 1
    assert history["summary"]["average_self_score"] == 100.0


def test_skill_assessment_requires_all_rubric_items_and_evidence(db, test_user):
    from jobfinder.market_service import create_skill_assessment, submit_skill_assessment
    skill = Skill(canonical_name="SQL", category="database", aliases_json="[]", active=True)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    attempt = create_skill_assessment(db, skill_id=skill.id)
    try:
        submit_skill_assessment(
            db, attempt["id"], response_text="", evidence_url="",
            rubric_answers={}, user_id=test_user.id,
        )
        assert False, "Era esperado exigir resposta e evidência."
    except ValueError as exc:
        assert "Responda a todos os critérios" in str(exc)

    answers = {criterion["id"]: False for criterion in attempt["criteria"]}
    try:
        submit_skill_assessment(
            db, attempt["id"], response_text="", evidence_url="",
            rubric_answers=answers,
            user_id=test_user.id,
        )
        assert False, "Era esperado exigir uma descrição ou link de evidência."
    except ValueError as exc:
        assert "Descreva sua solução" in str(exc)



def test_profile_gap_reassesses_skill_from_submitted_self_assessment(db, test_user):
    from jobfinder.market_service import (
        build_profile_gap, create_skill_assessment, submit_skill_assessment,
    )
    from jobfinder.models import Profile

    db.add(Profile(user_id=test_user.id, technologies="", skills="", keywords=""))
    db.commit()
    make_job(
        db,
        title="Estágio Python",
        description="Python é usado para desenvolver serviços e automatizar tarefas.",
    )
    snapshot = create_market_snapshot(db, level_scope="estagio", days=30, min_jobs=1)
    python_skill = db.scalar(select(Skill).where(Skill.canonical_name == "Python"))
    attempt = create_skill_assessment(db, user_id=test_user.id, skill_id=python_skill.id)
    answers = {item["id"]: True for item in attempt["criteria"]}
    submit_skill_assessment(
        db,
        attempt["id"],
        response_text="Implementei a solução, tratei erros, testei os cenários e documentei a execução.",
        evidence_url="https://github.com/example/python-evidence",
        rubric_answers=answers,
    )

    gap = build_profile_gap(db, run_id=snapshot["run_id"])
    python = next(item for item in gap["items"] if item["name"] == "Python")

    assert python["status"] == "autoavaliada"
    assert python["status_label"] == "Desafio prático autoavaliado"
    assert python["assessment"]["score"] == 100
    assert python["assessment"]["attempts_count"] == 1
    assert python["assessment"]["result_kind"] == "autoavaliação"
    assert "não comprovam domínio" in gap["notice"]


def test_profile_evidence_keeps_precedence_over_self_assessment(db, test_user):
    from jobfinder.market_service import (
        build_profile_gap, create_skill_assessment, submit_skill_assessment,
    )
    from jobfinder.models import Profile, PortfolioProject

    db.add(Profile(
        id=1,
        portfolio_projects=[PortfolioProject(
            name="Projeto React concluído",
            description="Aplicação web desenvolvida com React.",
            technologies="React",
            status="Concluído",
        )],
    ))
    db.commit()
    make_job(
        db,
        title="Estágio React",
        description="React é utilizado para construir interfaces web.",
    )
    snapshot = create_market_snapshot(db, level_scope="estagio", days=30, min_jobs=1)
    react_skill = db.scalar(select(Skill).where(Skill.canonical_name == "React"))
    attempt = create_skill_assessment(db, user_id=test_user.id, skill_id=react_skill.id)
    answers = {item["id"]: True for item in attempt["criteria"]}
    submit_skill_assessment(
        db,
        attempt["id"],
        response_text="Implementei uma interface funcional, tratei erros, testei e documentei o projeto.",
        evidence_url="https://github.com/example/react-evidence",
        rubric_answers=answers,
    )

    gap = build_profile_gap(db, run_id=snapshot["run_id"])
    react = next(item for item in gap["items"] if item["name"] == "React")

    assert react["status"] == "praticada"
    assert react["assessment"]["score"] == 100
