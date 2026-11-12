"""Persistência versionada das evidências extraídas do perfil profissional."""
from datetime import datetime
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .market import extract_skills
from .models import CareerEvidence, CareerEvidenceReview, Profile, Skill, SkillAssessmentAttempt


COMPLETED_VALUES = {"concluído", "concluido", "completed", "finalizado"}
IN_PROGRESS_VALUES = {"em andamento", "em desenvolvimento", "em curso", "em estudo", "in progress"}


def _status(value: str | None) -> str:
    return (value or "").strip().casefold()


def _sources(profile: Profile):
    """Produz fontes estáveis; IDs pertencem às coleções do próprio perfil."""
    for item in profile.experiences:
        yield (
            f"experience:{item.id}", "professional_experience", item.id,
            f'{item.role or "Experiência"} · {item.company or "Empresa não informada"}',
            f"{item.role} {item.company} {item.description}",
        )
    for item in profile.portfolio_projects:
        state = _status(item.status)
        kind = "completed_project" if state in COMPLETED_VALUES else "ongoing_project"
        yield (
            f"portfolio_project:{item.id}", kind, item.id, item.name or "Projeto",
            f"{item.name} {item.description} {item.technologies}",
        )
    for item in profile.courses:
        state = _status(item.status)
        kind = "completed_course" if state in COMPLETED_VALUES else (
            "ongoing_course" if state in IN_PROGRESS_VALUES else "course_status_unspecified"
        )
        yield (
            f"course:{item.id}", kind, item.id,
            f'{item.name or "Curso"} · {item.provider or "Instituição não informada"}',
            f"{item.name} {item.provider}",
        )
    for item in profile.certifications_items:
        yield (
            f"certification:{item.id}", "certification_record", item.id,
            f'{item.name or "Certificação"} · {item.issuer or "Emissor não informado"}',
            f"{item.name} {item.issuer}",
        )
    for item in profile.educations:
        yield (
            f"education:{item.id}", "education_record", item.id,
            f'{item.course or "Formação"} · {item.institution or "Instituição não informada"}',
            f"{item.course} {item.institution} {item.description}",
        )

    # Campos antigos continuam rastreáveis, sem serem confundidos com registros estruturados.
    yield ("legacy:experience", "legacy_experience", None, "Experiência (campo legado)", profile.experience or "")
    yield ("legacy:project", "legacy_project", None, "Projetos (campo legado)", profile.projects or "")
    yield ("legacy:certification", "legacy_certification", None, "Certificações (campo legado)", profile.certifications or "")
    yield ("legacy:technologies", "self_declared", None, "Tecnologias declaradas", profile.technologies or "")
    yield ("legacy:skills", "self_declared", None, "Habilidades declaradas", profile.skills or "")
    yield ("legacy:keywords", "self_declared", None, "Palavras-chave declaradas", profile.keywords or "")


def sync_profile_evidence(db: Session, profile: Profile, *, user_id: int) -> dict:
    """Sincroniza somente a conta informada; alterações criam versões, nunca sobrescrevem histórico."""
    desired = {}
    for source_key, source_type, source_id, label, source_text in _sources(profile):
        if not (source_text or "").strip():
            continue
        for skill in extract_skills(source_text, source_field=source_type):
            excerpt = " ".join((skill.get("evidence_text") or "").split())[:220]
            digest_input = f"{source_type}\n{excerpt.casefold()}"
            evidence_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
            key = (source_key, skill["canonical_name"], evidence_hash)
            desired[key] = {
                "source_key": source_key,
                "source_type": source_type,
                "source_id": source_id,
                "source_label": label[:300],
                "skill_name": skill["canonical_name"],
                "category": skill["category"],
                "excerpt": excerpt,
                "evidence_hash": evidence_hash,
            }

    existing = db.scalars(
        select(CareerEvidence).where(CareerEvidence.user_id == user_id)
    ).all()
    by_version = {
        (item.source_key, item.skill_name, item.evidence_hash): item
        for item in existing
    }
    now = datetime.utcnow()
    created = 0
    reactivated = 0
    for key, values in desired.items():
        item = by_version.get(key)
        if item is None:
            db.add(CareerEvidence(
                user_id=user_id,
                **values,
                verification_level="self_reported",
                is_active=True,
            ))
            created += 1
            continue
        if not item.is_active:
            reactivated += 1
        item.is_active = True
        item.superseded_at = None
        item.source_type = values["source_type"]
        item.source_id = values["source_id"]
        item.source_label = values["source_label"]
        item.category = values["category"]
        item.excerpt = values["excerpt"]
        item.verification_level = "self_reported"

    desired_keys = set(desired)
    superseded = 0
    for item in existing:
        key = (item.source_key, item.skill_name, item.evidence_hash)
        if item.is_active and key not in desired_keys:
            item.is_active = False
            item.superseded_at = now
            superseded += 1

    db.flush()
    return {
        "created": created,
        "reactivated": reactivated,
        "superseded": superseded,
        "active": len(desired),
    }


def list_profile_evidence(
    db: Session, *, user_id: int, active_only: bool = False, limit: int = 200
) -> list[dict]:
    """Lista evidências sem jamais aceitar user_id vindo do cliente."""
    stmt = select(CareerEvidence).where(CareerEvidence.user_id == user_id)
    if active_only:
        stmt = stmt.where(CareerEvidence.is_active.is_(True))
    rows = db.scalars(
        stmt.order_by(CareerEvidence.created_at.desc(), CareerEvidence.id.desc()).limit(limit)
    ).all()
    evidence_ids = [item.id for item in rows]
    reviews = db.scalars(
        select(CareerEvidenceReview)
        .where(
            CareerEvidenceReview.user_id == user_id,
            CareerEvidenceReview.evidence_id.in_(evidence_ids),
        )
        .order_by(CareerEvidenceReview.created_at.desc(), CareerEvidenceReview.id.desc())
    ).all() if evidence_ids else []
    latest_review = {}
    for review in reviews:
        latest_review.setdefault(review.evidence_id, review)

    return [
        {
            "id": item.id,
            "skill_name": item.skill_name,
            "category": item.category,
            "source_type": item.source_type,
            "source_key": item.source_key,
            "source_id": item.source_id,
            "source_label": item.source_label,
            "excerpt": item.excerpt,
            "verification_level": item.verification_level,
            "review_decision": latest_review[item.id].decision if item.id in latest_review else "pending",
            "review_note": latest_review[item.id].note if item.id in latest_review else "",
            "reviewed_at": latest_review[item.id].created_at.isoformat() if item.id in latest_review and latest_review[item.id].created_at else None,
            "verification_label": "Autodeclarada ou identificada em registro fornecido pela pessoa",
            "is_active": item.is_active,
            "superseded_at": item.superseded_at.isoformat() if item.superseded_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in rows
    ]


def record_self_assessment_evidence(
    db: Session, *, attempt_id: int, user_id: int
) -> dict:
    """Registra desafio enviado como autoavaliação, nunca como validação independente."""
    attempt = db.scalar(
        select(SkillAssessmentAttempt).where(
            SkillAssessmentAttempt.id == attempt_id,
            SkillAssessmentAttempt.user_id == user_id,
            SkillAssessmentAttempt.status == "self_reviewed",
        )
    )
    if attempt is None or attempt.submitted_at is None:
        raise ValueError("Autoavaliação não encontrada para esta conta.")
    skill = db.get(Skill, attempt.skill_id)
    if skill is None:
        raise ValueError("Competência da autoavaliação não encontrada.")

    response_excerpt = " ".join((attempt.response_text or "").split())[:220]
    evidence_url = (attempt.evidence_url or "").strip()
    excerpt = response_excerpt or (f"Link de evidência: {evidence_url}" if evidence_url else "")
    digest_input = f"self_assessment\\n{excerpt.casefold()}\\n{evidence_url}"
    evidence_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    source_key = f"challenge_attempt:{attempt.id}"

    item = db.scalar(
        select(CareerEvidence).where(
            CareerEvidence.user_id == user_id,
            CareerEvidence.source_key == source_key,
            CareerEvidence.skill_name == skill.canonical_name,
            CareerEvidence.evidence_hash == evidence_hash,
        )
    )
    if item is None:
        item = CareerEvidence(
            user_id=user_id,
            skill_name=skill.canonical_name,
            category=skill.category,
            source_type="self_assessment",
            source_key=source_key,
            source_id=attempt.id,
            source_label=attempt.challenge_title,
            excerpt=excerpt,
            evidence_hash=evidence_hash,
            verification_level="self_assessed",
            is_active=True,
        )
        db.add(item)
        created = True
    else:
        item.is_active = True
        item.superseded_at = None
        created = False

    db.flush()
    return {
        "created": created,
        "source_type": "self_assessment",
        "verification_level": "self_assessed",
        "notice": "Autoavaliação informada pela própria pessoa; não é validação independente de proficiência.",
    }



def review_profile_evidence(
    db: Session, *, evidence_id: int, user_id: int, decision: str, note: str = ""
) -> dict:
    """Anexa uma decisão humana; nunca altera a evidência ou seu nível de validação."""
    if decision not in {"confirmed", "dismissed"}:
        raise ValueError("Decisão inválida. Use confirmed ou dismissed.")
    item = db.scalar(
        select(CareerEvidence).where(
            CareerEvidence.id == evidence_id,
            CareerEvidence.user_id == user_id,
        )
    )
    if item is None:
        raise LookupError("Evidência não encontrada para esta conta.")
    if not item.is_active:
        raise ValueError("Não é possível revisar uma versão anterior da evidência.")
    clean_note = " ".join((note or "").split())[:1000]
    review = CareerEvidenceReview(
        user_id=user_id,
        evidence_id=item.id,
        decision=decision,
        note=clean_note,
    )
    db.add(review)
    db.flush()
    return {
        "id": review.id,
        "evidence_id": item.id,
        "decision": review.decision,
        "note": review.note,
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "verification_level": item.verification_level,
        "notice": (
            "Confirmação humana do registro, não validação independente de proficiência."
            if decision == "confirmed"
            else "Registro marcado como não relevante; a evidência original foi preservada."
        ),
    }
