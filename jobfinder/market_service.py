"""Persistência de competências e snapshots de inteligência de mercado."""
import json
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from .market import SKILL_CATALOG, extract_skills, taxonomy_version
from .models import Job, Skill, JobSkill, MarketAnalysisRun, MarketSkillMetric, MarketSkillPair

EXTRACTOR_VERSION = "dictionary-1"


def sync_skill_catalog(db: Session) -> dict[str, Skill]:
    """Cria/atualiza o catálogo sem apagar competências já referenciadas."""
    result = {}
    for item in SKILL_CATALOG:
        skill = db.scalar(select(Skill).where(Skill.canonical_name == item["name"]))
        aliases = json.dumps(item["aliases"], ensure_ascii=False)
        if skill is None:
            skill = Skill(
                canonical_name=item["name"], category=item["category"],
                aliases_json=aliases, taxonomy_version=taxonomy_version(), active=True,
            )
            db.add(skill)
        else:
            skill.category = item["category"]
            skill.aliases_json = aliases
            skill.taxonomy_version = taxonomy_version()
            skill.active = True
        result[item["name"]] = skill
    db.flush()
    return result


def index_job_skills(db: Session, job: Job, *, reprocess: bool = False) -> int:
    """Extrai e persiste evidências do título e descrição de uma vaga."""
    catalog = sync_skill_catalog(db)
    existing = db.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all()
    if existing and not reprocess:
        return len(existing)
    if existing:
        for row in existing:
            db.delete(row)
        db.flush()

    texts = [("title", job.title or ""), ("description", job.description or "")]
    evidence_by_name = {}
    for field, value in texts:
        for item in extract_skills(value, source_field=field):
            current = evidence_by_name.get(item["canonical_name"])
            # Prefere evidência da descrição, que normalmente contém mais contexto.
            if current is None or field == "description":
                evidence_by_name[item["canonical_name"]] = item

    for name, evidence in evidence_by_name.items():
        skill = catalog.get(name)
        if skill is None:
            continue
        db.add(JobSkill(
            job_id=job.id, skill_id=skill.id,
            evidence_text=evidence["evidence_text"],
            evidence_field=evidence["evidence_field"],
            extraction_method=evidence["extraction_method"],
            confidence=evidence["confidence"],
            extractor_version=EXTRACTOR_VERSION,
        ))
    db.flush()
    return len(evidence_by_name)


def index_unprocessed_jobs(db: Session, *, limit: int = 500) -> dict:
    """Indexa vagas elegíveis ainda sem evidências; execução pode ser repetida."""
    jobs = db.scalars(
        select(Job)
        .where(Job.level.in_({"estagio", "junior"}))
        .order_by(Job.id)
        .limit(max(1, min(limit, 5000)))
    ).all()
    indexed = 0
    for job in jobs:
        existing = db.scalar(select(JobSkill.id).where(JobSkill.job_id == job.id).limit(1))
        if existing is None:
            indexed += index_job_skills(db, job)
    db.commit()
    return {"jobs_scanned": len(jobs), "jobs_indexed": indexed}


def create_market_snapshot(
    db: Session, *, level_scope: str = "both", days: int = 30, min_jobs: int = 30
) -> dict:
    """Gera snapshot usando created_at (primeira observação local), nunca data presumida."""
    if level_scope not in {"both", "estagio", "junior"}:
        raise ValueError("level_scope deve ser both, estagio ou junior")
    days = max(1, min(int(days), 365))
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    levels = ["estagio", "junior"] if level_scope == "both" else [level_scope]

    stmt = select(Job).where(
        Job.level.in_(levels), Job.created_at >= start, Job.created_at <= now
    )
    jobs = db.scalars(stmt.order_by(Job.id)).all()
    job_ids = [job.id for job in jobs]
    sources = sorted({job.source for job in jobs if job.source})
    with_description = sum(1 for job in jobs if len((job.description or "").strip()) >= 80)

    run = MarketAnalysisRun(
        period_start=start, period_end=now, level_scope=level_scope,
        area_scope="technology", filters_json=json.dumps({"days": days, "levels": levels}),
        total_jobs=len(jobs), valid_jobs=len(jobs), jobs_with_description=with_description,
        sources_json=json.dumps(sources, ensure_ascii=False),
        taxonomy_version=taxonomy_version(), extractor_version=EXTRACTOR_VERSION,
        status="running",
    )
    db.add(run)
    db.flush()

    for job in jobs:
        index_job_skills(db, job)

    if job_ids:
        rows = db.execute(
            select(JobSkill.skill_id, JobSkill.job_id)
            .where(JobSkill.job_id.in_(job_ids))
        ).all()
    else:
        rows = []

    skill_jobs = {}
    for skill_id, job_id in rows:
        skill_jobs.setdefault(skill_id, set()).add(job_id)

    skill_ids = list(skill_jobs)
    skill_names = {
        item.id: item.canonical_name
        for item in db.scalars(select(Skill).where(Skill.id.in_(skill_ids))).all()
    } if skill_ids else {}

    ranked = sorted(
        skill_jobs.items(),
        key=lambda pair: (-len(pair[1]), skill_names.get(pair[0], "")),
    )
    for rank, (skill_id, job_set) in enumerate(ranked, start=1):
        db.add(MarketSkillMetric(
            run_id=run.id, skill_id=skill_id, jobs_count=len(job_set),
            mention_rate=(len(job_set) / len(jobs)) if jobs else 0.0, rank=rank,
        ))

    # Conta cada par uma única vez por vaga.
    pair_counts = Counter()
    for job_id in job_ids:
        ids = sorted({skill_id for skill_id, candidate_job in rows if candidate_job == job_id})
        for index, skill_a in enumerate(ids):
            for skill_b in ids[index + 1:]:
                pair_counts[(skill_a, skill_b)] += 1
    for (skill_a, skill_b), count in pair_counts.items():
        db.add(MarketSkillPair(
            run_id=run.id, skill_a_id=skill_a, skill_b_id=skill_b,
            jobs_count=count, pair_rate=(count / len(jobs)) if jobs else 0.0,
        ))

    notes = []
    if len(jobs) < min_jobs:
        notes.append(f"Amostra insuficiente para ranking conclusivo: {len(jobs)} vagas; mínimo configurado: {min_jobs}.")
    if with_description < len(jobs):
        notes.append(f"{len(jobs) - with_description} vagas têm descrição ausente ou curta.")
    run.quality_notes = " ".join(notes)
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(run)

    return {
        "run_id": run.id, "status": run.status, "period_start": run.period_start.isoformat(),
        "period_end": run.period_end.isoformat(), "level_scope": run.level_scope,
        "total_jobs": run.total_jobs, "valid_jobs": run.valid_jobs,
        "jobs_with_description": run.jobs_with_description,
        "sources": sources, "sample_sufficient": len(jobs) >= min_jobs,
        "quality_notes": run.quality_notes,
        "skills_detected": len(ranked), "skill_pairs_detected": len(pair_counts),
    }
