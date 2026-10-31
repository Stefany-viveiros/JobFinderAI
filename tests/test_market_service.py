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


def test_profile_gap_distinguishes_project_course_declaration_and_missing(db):
    from jobfinder.market_service import build_profile_gap
    from jobfinder.models import Profile, PortfolioProject, Course

    profile = Profile(
        id=1,
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
        description="Python, React e JavaScript são competências desejáveis para esta vaga.",
    )
    snapshot = create_market_snapshot(db, level_scope="estagio", days=30, min_jobs=1)
    gap = build_profile_gap(db, run_id=snapshot["run_id"])
    by_name = {item["name"]: item for item in gap["items"]}

    assert by_name["React"]["status"] == "praticada"
    assert by_name["Python"]["status"] == "curso_concluido"
    assert by_name["JavaScript"]["status"] == "declarada"
    assert gap["available"] is True
    assert "não significa falta de conhecimento" in gap["notice"]
