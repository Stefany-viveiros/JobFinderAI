"""Persistência versionada das evidências extraídas do perfil profissional."""
from datetime import datetime
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .market import extract_skills
from .models import CareerEvidence, Profile


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
            "verification_label": "Autodeclarada ou identificada em registro fornecido pela pessoa",
            "is_active": item.is_active,
            "superseded_at": item.superseded_at.isoformat() if item.superseded_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in rows
    ]
