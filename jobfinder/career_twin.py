"""Career Twin: visão consolidada e rastreável do perfil profissional.

A primeira versão é um read model determinístico: não persiste cópias do perfil,
não atribui nível de proficiência e não transforma ausência de menção em ausência
de conhecimento.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .market import extract_skills
from .models import (
    MarketAnalysisRun,
    MarketSkillMetric,
    Profile,
    Skill,
    SkillAssessmentAttempt,
    DevelopmentPlanItem,
)


COMPLETED_VALUES = {"concluído", "concluido", "completed", "finalizado"}
IN_PROGRESS_VALUES = {"em andamento", "em desenvolvimento", "em curso", "em estudo", "in progress"}


def _status(value: str | None) -> str:
    return (value or "").strip().casefold()


def _record_evidence(source_type: str, source_label: str, source_id: int | None, text: str):
    found = extract_skills(text, source_field=source_type)
    return [
        {
            "canonical_name": item["canonical_name"],
            "category": item["category"],
            "source_type": source_type,
            "source_label": source_label,
            "source_id": source_id,
            "excerpt": item["evidence_text"],
        }
        for item in found
    ]


def _public_profile(profile: Profile) -> dict:
    def records(items, fields):
        return [
            {"id": item.id, **{field: getattr(item, field) for field in fields}}
            for item in items
        ]

    return {
        "id": profile.id,
        "name": profile.name or "",
        "course": profile.course or "",
        "institution": profile.institution or "",
        "academic_stage": profile.academic_stage or "",
        "interests": profile.interests or "",
        "location": profile.location or "",
        "modality": profile.modality or "",
        "job_types": profile.job_types or "",
        "educations": records(profile.educations, (
            "course", "institution", "degree", "status", "start_date", "end_date", "description"
        )),
        "experiences": records(profile.experiences, (
            "company", "role", "employment_type", "location", "start_date", "end_date",
            "is_current", "description"
        )),
        "courses": records(profile.courses, (
            "name", "provider", "workload", "completed_at", "status", "credential_url"
        )),
        "certifications": records(profile.certifications_items, (
            "name", "issuer", "issued_at", "expires_at", "credential_id", "credential_url"
        )),
        "projects": records(profile.portfolio_projects, (
            "name", "description", "technologies", "repository_url", "demo_url", "status"
        )),
    }


def build_career_twin(db: Session, *, user_id: int) -> dict:
    """Monta o Career Twin exclusivamente a partir dos registros da conta autenticada."""
    profile = db.scalar(
        select(Profile)
        .where(Profile.user_id == user_id)
        .options(
            selectinload(Profile.educations),
            selectinload(Profile.experiences),
            selectinload(Profile.courses),
            selectinload(Profile.certifications_items),
            selectinload(Profile.portfolio_projects),
        )
    )
    if profile is None:
        return {
            "available": False,
            "message": "Seu perfil ainda não foi criado. Preencha o perfil profissional para montar seu Career Twin.",
        }

    evidence_by_skill = defaultdict(list)

    def add(source_type: str, label: str, source_id: int | None, value: str):
        if not (value or "").strip():
            return
        for evidence in _record_evidence(source_type, label, source_id, value):
            evidence_by_skill[evidence["canonical_name"]].append(evidence)

    for item in profile.experiences:
        add("professional_experience", f'{item.role or "Experiência"} · {item.company or "Empresa não informada"}', item.id,
            f"{item.role} {item.company} {item.description}")

    for item in profile.portfolio_projects:
        state = _status(item.status)
        source_type = "completed_project" if state in COMPLETED_VALUES else "ongoing_project"
        add(source_type, item.name or "Projeto", item.id,
            f"{item.name} {item.description} {item.technologies}")

    for item in profile.courses:
        state = _status(item.status)
        source_type = "completed_course" if state in COMPLETED_VALUES else (
            "ongoing_course" if state in IN_PROGRESS_VALUES else "course_status_unspecified"
        )
        add(source_type, f'{item.name or "Curso"} · {item.provider or "Instituição não informada"}', item.id,
            f"{item.name} {item.provider}")

    for item in profile.certifications_items:
        add("certification_record", f'{item.name or "Certificação"} · {item.issuer or "Emissor não informado"}', item.id,
            f"{item.name} {item.issuer}")

    for item in profile.educations:
        add("education_record", f'{item.course or "Formação"} · {item.institution or "Instituição não informada"}', item.id,
            f"{item.course} {item.institution} {item.description}")

    # Campos legados continuam disponíveis e suas origens são identificadas.
    add("legacy_experience", "Experiência (campo legado)", None, profile.experience or "")
    add("legacy_project", "Projetos (campo legado)", None, profile.projects or "")
    add("legacy_certification", "Certificações (campo legado)", None, profile.certifications or "")
    add("self_declared", "Tecnologias declaradas", None, profile.technologies or "")
    add("self_declared", "Habilidades declaradas", None, profile.skills or "")
    add("self_declared", "Palavras-chave declaradas", None, profile.keywords or "")

    assessment_rows = db.execute(
        select(SkillAssessmentAttempt, Skill)
        .join(Skill, Skill.id == SkillAssessmentAttempt.skill_id)
        .where(
            SkillAssessmentAttempt.user_id == user_id,
            SkillAssessmentAttempt.status == "self_reviewed",
        )
        .order_by(SkillAssessmentAttempt.submitted_at.desc(), SkillAssessmentAttempt.id.desc())
    ).all()
    assessments_by_skill = {}
    for attempt, skill in assessment_rows:
        if skill.canonical_name not in assessments_by_skill:
            assessments_by_skill[skill.canonical_name] = {
                "attempt_id": attempt.id,
                "title": attempt.challenge_title,
                "score": attempt.score,
                "feedback": attempt.feedback or "",
                "evidence_url": attempt.evidence_url or "",
                "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
                "result_kind": "self_assessment",
                "notice": "Autoavaliação informada pela própria pessoa; não é validação independente de proficiência.",
            }

    run = db.scalar(
        select(MarketAnalysisRun)
        .where(MarketAnalysisRun.status == "completed")
        .order_by(MarketAnalysisRun.created_at.desc(), MarketAnalysisRun.id.desc())
        .limit(1)
    )
    market_by_skill = {}
    market_payload = None
    if run is not None:
        metric_rows = db.execute(
            select(MarketSkillMetric, Skill)
            .join(Skill, Skill.id == MarketSkillMetric.skill_id)
            .where(MarketSkillMetric.run_id == run.id)
            .order_by(MarketSkillMetric.rank)
        ).all()
        for metric, skill in metric_rows:
            market_by_skill[skill.canonical_name] = {
                "skill_id": skill.id,
                "jobs_count": metric.jobs_count,
                "category": skill.category,
                "mention_rate": round(metric.mention_rate * 100, 1),
                "rank": metric.rank,
                "run_id": run.id,
            }
        market_payload = {
            "run_id": run.id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "period_start": run.period_start.isoformat() if run.period_start else None,
            "period_end": run.period_end.isoformat() if run.period_end else None,
            "level_scope": run.level_scope,
            "valid_jobs": run.valid_jobs,
            "jobs_with_description": run.jobs_with_description,
            "quality_notes": run.quality_notes or "",
        }

    skill_names = set(evidence_by_skill) | set(assessments_by_skill) | set(market_by_skill)
    skills = []
    for name in sorted(skill_names, key=str.casefold):
        evidence = evidence_by_skill.get(name, [])
        assessment = assessments_by_skill.get(name)
        market = market_by_skill.get(name)
        if any(item["source_type"] == "professional_experience" for item in evidence):
            status = "professional_experience"
            status_label = "Mencionada em experiência profissional"
        elif any(item["source_type"] == "completed_project" for item in evidence):
            status = "completed_project"
            status_label = "Mencionada em projeto concluído"
        elif any(item["source_type"] == "ongoing_project" for item in evidence):
            status = "ongoing_project"
            status_label = "Mencionada em projeto em andamento"
        elif any(item["source_type"] == "self_declared" for item in evidence):
            status = "self_declared"
            status_label = "Declarada no perfil"
        elif evidence:
            status = evidence[0]["source_type"]
            status_label = "Mencionada em registro acadêmico ou de aprendizagem"
        elif assessment:
            status = "self_assessed"
            status_label = "Possui autoavaliação registrada"
        else:
            status = "not_found"
            status_label = "Não identificada nos registros disponíveis"

        skills.append({
            "name": name,
            "category": next((item["category"] for item in evidence), market.get("category") if market else None),
            "status": status,
            "status_label": status_label,
            "evidence": evidence,
            "self_assessment": assessment,
            "market": market,
            "interpretation": (
                "A ausência de menção não significa ausência de conhecimento."
                if status == "not_found"
                else "A origem indica onde a competência foi mencionada; não representa, por si só, nível de proficiência."
            ),
        })

    # Linha do tempo derivada de registros datados e eventos de desenvolvimento.
    # Uma atividade concluída ou autoavaliação não é promovida automaticamente a proficiência.
    timeline = []

    def add_event(event_type, title, detail="", date_value=None, status="", source_type="", source_id=None, evidence_url=""):
        if hasattr(date_value, "isoformat"):
            date_text = date_value.isoformat()
        else:
            date_text = str(date_value or "").strip() or None
        timeline.append({
            "event_type": event_type,
            "title": str(title or "").strip(),
            "detail": str(detail or "").strip(),
            "date": date_text,
            "status": str(status or "").strip(),
            "source_type": source_type,
            "source_id": source_id,
            "evidence_url": str(evidence_url or "").strip(),
        })

    for item in profile.educations:
        date_value = item.end_date or item.start_date or None
        add_event(
            "education_record", item.course or "Formação acadêmica",
            " · ".join(x for x in (item.institution, item.degree, item.status) if x),
            date_value, item.status, "education_record", item.id,
        )

    for item in profile.experiences:
        period = " – ".join(x for x in (item.start_date, item.end_date or ("Atual" if item.is_current else "")) if x)
        add_event(
            "professional_experience", item.role or "Experiência profissional",
            " · ".join(x for x in (item.company, period, item.employment_type) if x),
            item.end_date or item.start_date or None,
            "Atual" if item.is_current else "Experiência registrada",
            "professional_experience", item.id,
        )

    for item in profile.portfolio_projects:
        state = _status(item.status)
        add_event(
            "completed_project" if state in COMPLETED_VALUES else "ongoing_project",
            item.name or "Projeto de portfólio",
            item.description or item.technologies or "Projeto registrado no portfólio.",
            None, item.status, "portfolio_project", item.id,
            item.repository_url or item.demo_url or "",
        )

    for item in profile.courses:
        add_event(
            "completed_course" if _status(item.status) in COMPLETED_VALUES else "ongoing_course",
            item.name or "Curso",
            " · ".join(x for x in (item.provider, item.workload, item.status) if x),
            item.completed_at or None,
            item.status, "course_record", item.id, item.credential_url or "",
        )

    for item in profile.certifications_items:
        add_event(
            "certification_record", item.name or "Certificação",
            " · ".join(x for x in (item.issuer, item.credential_id) if x),
            item.issued_at or None, "Certificação cadastrada",
            "certification_record", item.id, item.credential_url or "",
        )

    plan_rows = db.execute(
        select(DevelopmentPlanItem, Skill)
        .join(Skill, Skill.id == DevelopmentPlanItem.skill_id)
        .where(DevelopmentPlanItem.user_id == user_id)
        .order_by(DevelopmentPlanItem.created_at.desc(), DevelopmentPlanItem.id.desc())
    ).all()
    for item, skill in plan_rows:
        add_event(
            "development_goal_created", item.title or f"Desenvolver {skill.canonical_name}",
            f"Meta de desenvolvimento para {skill.canonical_name}. {item.objective or ''}".strip(),
            item.created_at, item.status, "development_plan_item", item.id,
            item.resource_url or "",
        )
        if item.completed_at:
            add_event(
                "development_goal_completed", f"Meta concluída: {skill.canonical_name}",
                "Atividade marcada como concluída. Isso registra a execução da meta, não comprova proficiência por si só.",
                item.completed_at, "completed", "development_plan_item", item.id,
                item.resource_url or "",
            )

    all_attempts = db.scalars(
        select(SkillAssessmentAttempt)
        .where(SkillAssessmentAttempt.user_id == user_id)
        .order_by(SkillAssessmentAttempt.created_at.desc(), SkillAssessmentAttempt.id.desc())
    ).all()
    for attempt in all_attempts:
        skill = db.get(Skill, attempt.skill_id)
        skill_name = skill.canonical_name if skill else "Competência"
        add_event(
            "challenge_started", attempt.challenge_title or f"Desafio de {skill_name}",
            f"Desafio prático iniciado para {skill_name}.",
            attempt.created_at, attempt.status, "skill_assessment_attempt", attempt.id,
        )
        if attempt.submitted_at:
            add_event(
                "self_assessment_submitted", f"Autoavaliação registrada: {skill_name}",
                f"Resultado autoavaliado: {attempt.score if attempt.score is not None else 'sem pontuação'}%. Não representa validação independente.",
                attempt.submitted_at, "self_reviewed", "skill_assessment_attempt", attempt.id,
                attempt.evidence_url or "",
            )

    # Eventos com data conhecida aparecem primeiro, do mais recente para o mais antigo.
    timeline.sort(key=lambda item: item["date"] or "", reverse=True)
    timeline.sort(key=lambda item: item["date"] is None)

    public_profile = _public_profile(profile)
    sections = {
        "identity": bool(public_profile["name"] or public_profile["interests"]),
        "education": bool(public_profile["educations"] or public_profile["course"]),
        "experience": bool(public_profile["experiences"] or profile.experience),
        "projects": bool(public_profile["projects"] or profile.projects),
        "learning": bool(public_profile["courses"] or public_profile["certifications"]),
        "skills": bool(profile.technologies or profile.skills or profile.keywords or skills),
    }
    completed_sections = sum(sections.values())
    return {
        "available": True,
        "profile": public_profile,
        "summary": {
            "completed_sections": completed_sections,
            "total_sections": len(sections),
            "skills_identified": sum(bool(item["evidence"] or item["self_assessment"]) for item in skills),
            "skills_with_evidence": sum(bool(item["evidence"]) for item in skills),
            "skills_with_self_assessment": sum(bool(item["self_assessment"]) for item in skills),
            "skills_not_found_in_profile": sum(item["status"] == "not_found" for item in skills),
        },
        "sections": sections,
        "skills": skills,
        "timeline": timeline,
        "market": market_payload,
        "data_quality": {
            "method": "extração determinística por taxonomia e aliases do JobFinder AI",
            "warnings": [
                "Menção textual não comprova domínio técnico.",
                "Cursos e certificações são registros de aprendizagem, não validações automáticas de proficiência.",
                "Desafios atuais são autoavaliações, não avaliações independentes.",
                "Competências não identificadas podem existir e não devem ser tratadas como ausentes.",
            ],
        },
    }
