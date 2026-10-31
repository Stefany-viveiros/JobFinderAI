"""Persistência de competências e snapshots de inteligência de mercado."""
import json
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from .market import SKILL_CATALOG, extract_skills, taxonomy_version
from .models import Job, Skill, JobSkill, JobSkillExtraction, MarketAnalysisRun, MarketSkillMetric, MarketSkillPair, DevelopmentPlanItem

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


def index_job_skills(db: Session, job: Job, *, reprocess: bool = False, catalog=None) -> int:
    """Extrai e persiste evidências do título e descrição de uma vaga."""
    catalog = catalog or sync_skill_catalog(db)
    extraction = db.scalar(
        select(JobSkillExtraction).where(JobSkillExtraction.job_id == job.id)
    )
    if extraction and extraction.extractor_version == EXTRACTOR_VERSION and not reprocess:
        return extraction.skills_found
    existing = db.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all()
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
    if extraction is None:
        extraction = JobSkillExtraction(job_id=job.id)
        db.add(extraction)
    extraction.extractor_version = EXTRACTOR_VERSION
    extraction.skills_found = len(evidence_by_name)
    extraction.indexed_at = datetime.utcnow()
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
    catalog = sync_skill_catalog(db)
    for job in jobs:
        extraction = db.scalar(
            select(JobSkillExtraction).where(JobSkillExtraction.job_id == job.id)
        )
        if extraction is None or extraction.extractor_version != EXTRACTOR_VERSION:
            indexed += 1
            index_job_skills(db, job, catalog=catalog)
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

    catalog = sync_skill_catalog(db)
    for job in jobs:
        index_job_skills(db, job, catalog=catalog)

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
    skills_by_job = {}
    for skill_id, job_id in rows:
        skills_by_job.setdefault(job_id, set()).add(skill_id)
    for job_id in job_ids:
        ids = sorted(skills_by_job.get(job_id, set()))
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


def build_profile_gap(db: Session, *, run_id: int | None = None) -> dict:
    """Cruza competências demandadas no snapshot com evidências explícitas do perfil."""
    from .models import Profile

    profile = db.get(Profile, 1)
    if profile is None:
        return {"available": False, "message": "Cadastre seu perfil para comparar as competências."}

    run = db.get(MarketAnalysisRun, run_id) if run_id else db.scalar(
        select(MarketAnalysisRun)
        .where(MarketAnalysisRun.status == "completed")
        .order_by(MarketAnalysisRun.created_at.desc(), MarketAnalysisRun.id.desc())
        .limit(1)
    )
    if run is None:
        return {"available": False, "message": "Gere uma análise de mercado antes de consultar o Skill Gap."}

    metric_rows = db.execute(
        select(MarketSkillMetric, Skill)
        .join(Skill, Skill.id == MarketSkillMetric.skill_id)
        .where(MarketSkillMetric.run_id == run.id)
        .order_by(MarketSkillMetric.rank)
    ).all()

    # Cada campo é analisado separadamente para preservar a origem da evidência.
    profile_texts = {
        "experiencia": " ".join(
            f"{item.role} {item.company} {item.description}"
            for item in profile.experiences
        ) + " " + (profile.experience or ""),
        "praticada": " ".join(
            f"{item.name} {item.description} {item.technologies}"
            for item in profile.portfolio_projects
            if (item.status or "").strip().lower() in {"concluído", "concluido", "completed"}
        ),
        "projeto": " ".join(
            f"{item.name} {item.description} {item.technologies}"
            for item in profile.portfolio_projects
            if (item.status or "").strip().lower() not in {"concluído", "concluido", "completed"}
        ) + " " + (profile.projects or ""),
        "formacao": " ".join(
            f"{item.course} {item.description}"
            for item in profile.educations
        ),
        "curso_concluido": " ".join(
            f"{item.name} {item.provider}"
            for item in profile.courses
            if (item.status or "").strip().lower() in {"concluído", "concluido", "completed"}
        ),
        "em_estudo": " ".join([
            *[
                f"{item.name} {item.provider}"
                for item in profile.courses
                if (item.status or "").strip().lower() in {"em andamento", "em curso", "in progress", "em estudo"}
            ],
            *[
                f"{item.name} {item.description} {item.technologies}"
                for item in profile.portfolio_projects
                if (item.status or "").strip().lower() in {"em desenvolvimento", "em andamento", "in progress"}
            ],
        ]),
        "certificacao": " ".join(
            f"{item.name} {item.issuer}"
            for item in profile.certifications_items
        ) + " " + (profile.certifications or ""),
        "declarada": " ".join([
            profile.technologies or "", profile.skills or "", profile.keywords or "",
        ]),
    }

    detected = {
        source: {item["canonical_name"] for item in extract_skills(value, source_field=source)}
        for source, value in profile_texts.items()
    }
    priorities = {
        "experiencia": (1, "Evidenciada em experiência profissional"),
        "praticada": (2, "Praticada em projeto concluído"),
        "projeto": (3, "Evidenciada em projeto em desenvolvimento"),
        "curso_concluido": (4, "Mencionada em curso concluído"),
        "certificacao": (5, "Mencionada em certificação"),
        "em_estudo": (6, "Em estudo ou prática em andamento"),
        "formacao": (7, "Mencionada na formação acadêmica"),
        "declarada": (8, "Declarada no perfil"),
    }

    items = []
    for metric, skill in metric_rows:
        evidence = [
            {"source": source, "label": priorities[source][1]}
            for source in priorities if skill.canonical_name in detected[source]
        ]
        if evidence:
            status = evidence[0]["source"]
            status_label = priorities[status][1]
        else:
            status = "nao_identificada"
            status_label = "Não identificada no perfil"

        demand_rate = round(metric.mention_rate * 100, 1)
        if status == "nao_identificada" and metric.rank <= 5:
            recommendation = "Entre as mais citadas neste recorte; avaliar prioridade"
        elif status == "nao_identificada":
            recommendation = "Acompanhar a demanda"
        elif status in {"em_estudo", "curso_concluido", "certificacao", "formacao", "projeto"}:
            recommendation = "Considerar prática em projeto"
        else:
            recommendation = "Fortalecer e demonstrar com evidências"

        items.append({
            "skill_id": skill.id,
            "name": skill.canonical_name,
            "category": skill.category,
            "jobs_count": metric.jobs_count,
            "mention_rate": demand_rate,
            "status": status,
            "status_label": status_label,
            "evidence": evidence,
            "recommendation": recommendation,
        })

    counts = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    return {
        "available": True,
        "run_id": run.id,
        "total_skills": len(items),
        "counts": counts,
        "items": items,
        "notice": "O cruzamento identifica menções textuais no perfil. Curso, certificação ou projeto não comprovam domínio; ausência de menção não significa falta de conhecimento.",
    }


DEVELOPMENT_STATUSES = {"planned", "in_progress", "completed", "paused"}


def development_item_dict(item: "DevelopmentPlanItem", skill: Skill) -> dict:
    return {
        "id": item.id,
        "skill_id": skill.id,
        "skill_name": skill.canonical_name,
        "category": skill.category,
        "source_run_id": item.source_run_id,
        "title": item.title,
        "objective": item.objective,
        "activity": item.activity,
        "resource_url": item.resource_url,
        "estimated_hours": item.estimated_hours,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "status": item.status,
        "progress_percent": item.progress_percent,
        "notes": item.notes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def list_development_plan(db: Session) -> dict:
    from .models import DevelopmentPlanItem
    rows = db.execute(
        select(DevelopmentPlanItem, Skill)
        .join(Skill, Skill.id == DevelopmentPlanItem.skill_id)
        .order_by(
            DevelopmentPlanItem.due_date.is_(None),
            DevelopmentPlanItem.due_date,
            DevelopmentPlanItem.created_at.desc(),
        )
    ).all()
    items = [development_item_dict(item, skill) for item, skill in rows]
    total = len(items)
    completed = sum(item["status"] == "completed" for item in items)
    active = sum(item["status"] == "in_progress" for item in items)
    hours = sum(item["estimated_hours"] for item in items)
    return {
        "items": items,
        "summary": {
            "total": total, "completed": completed, "in_progress": active,
            "planned": sum(item["status"] == "planned" for item in items),
            "estimated_hours": hours,
            "completion_rate": round((completed / total) * 100, 1) if total else 0,
        },
    }


def create_development_item(
    db: Session, *, skill_id: int, run_id: int | None = None,
    title: str | None = None, objective: str = "", activity: str = "",
    estimated_hours: int = 4, due_date=None, resource_url: str = "",
) -> dict:
    from .models import DevelopmentPlanItem

    skill = db.get(Skill, skill_id)
    if skill is None or not skill.active:
        raise ValueError("Competência não encontrada no catálogo.")
    if run_id is not None:
        run = db.get(MarketAnalysisRun, run_id)
        if run is None or run.status != "completed":
            raise ValueError("Análise de mercado não encontrada.")
        metric_exists = db.scalar(
            select(MarketSkillMetric.id).where(
                MarketSkillMetric.run_id == run_id,
                MarketSkillMetric.skill_id == skill_id,
            )
        )
        if metric_exists is None:
            raise ValueError("A competência não pertence à análise selecionada.")
    duplicate = db.scalar(
        select(DevelopmentPlanItem).where(
            DevelopmentPlanItem.skill_id == skill_id,
            DevelopmentPlanItem.status.in_({"planned", "in_progress", "paused"}),
        ).limit(1)
    )
    if duplicate:
        raise ValueError("Já existe uma meta ativa para esta competência no seu plano.")
    category = (skill.category or "").lower()
    if not activity:
        if any(term in category for term in ("framework", "library", "language", "web")):
            activity = f"Estude os fundamentos de {skill.canonical_name} e desenvolva uma pequena aplicação que demonstre seu uso."
        elif any(term in category for term in ("banco", "database")):
            activity = f"Modele um banco de dados simples usando {skill.canonical_name}, faça consultas e documente as decisões."
        elif any(term in category for term in ("cloud", "infra")):
            activity = f"Faça uma atividade prática guiada com {skill.canonical_name} e registre configuração, etapas e resultado."
        else:
            activity = f"Pesquise os fundamentos de {skill.canonical_name}, pratique em um cenário pequeno e registre o que conseguiu realizar."
    item = DevelopmentPlanItem(
        skill_id=skill_id,
        source_run_id=run_id,
        title=(title or f"Desenvolver {skill.canonical_name}").strip(),
        objective=(objective or f"Construir evidência prática de contato com {skill.canonical_name}.").strip(),
        activity=activity.strip(),
        resource_url=resource_url.strip(),
        estimated_hours=estimated_hours,
        due_date=due_date,
        status="planned",
        progress_percent=0,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return development_item_dict(item, skill)


def update_development_item(db: Session, item_id: int, payload: dict) -> dict:
    from .models import DevelopmentPlanItem

    item = db.get(DevelopmentPlanItem, item_id)
    if item is None:
        raise ValueError("Meta de desenvolvimento não encontrada.")
    allowed = {"status", "progress_percent", "due_date", "notes", "title", "objective", "activity", "estimated_hours", "resource_url"}
    for key, value in payload.items():
        if key in allowed:
            setattr(item, key, value)
    if item.status == "completed":
        item.progress_percent = 100
        item.completed_at = datetime.utcnow()
    else:
        item.completed_at = None
        if item.progress_percent == 100:
            item.progress_percent = 99
    db.commit()
    db.refresh(item)
    skill = db.get(Skill, item.skill_id)
    return development_item_dict(item, skill)
