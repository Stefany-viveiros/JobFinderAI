"""Agente de candidaturas: buscar → normalizar/deduplicar → avaliar → preparar → (aprovar) → enviar → registrar."""
from sqlalchemy import select

from . import applying
from .models import AgentSettings, ApplicationAttempt, Application, Job
from .service import collect_and_save_ranked, get_profile
from .sources import SOURCES, collect_selected

MAX_PREPARE_PER_RUN = 20
TARGET_LEVELS = ("estagio", "junior")


def get_agent_settings(db, user_id=None) -> AgentSettings:
    """Carrega configuração individual; modo legado existe apenas para testes/rotinas antigas."""
    if user_id is None:
        s = db.get(AgentSettings, 1)
        if not s:
            s = AgentSettings(id=1)
            db.add(s)
            db.commit()
            db.refresh(s)
        return s
    s = db.scalar(select(AgentSettings).where(AgentSettings.user_id == user_id))
    if s is None:
        s = AgentSettings(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def pick_candidates(db, min_score, limit=MAX_PREPARE_PER_RUN, user_id=None):
    """Vagas estágio/júnior compatíveis, sem candidatura e sem tentativa anterior (inclui falhas/canceladas)."""
    attempted = select(ApplicationAttempt.job_id)
    applied = select(Application.job_id)
    if user_id is not None:
        attempted = attempted.where(ApplicationAttempt.user_id == user_id)
        applied = applied.where(Application.user_id == user_id)
    stmt = (select(Job).where(
                Job.is_archived.is_(False),
                Job.level.in_(TARGET_LEVELS),
                Job.compatibility >= min_score,
                Job.missing_reasons.not_like("%Requisito(s) obrigatório(s) não identificado(s)%"),
                Job.id.not_in(attempted),
                Job.id.not_in(applied),
            )
            .order_by(Job.compatibility.desc(), Job.id.desc()).limit(limit))
    return list(db.scalars(stmt).all())


def run_agent(db, sources=None, limit=80, collect=True, collector=collect_selected, user_id=None):
    settings_row = get_agent_settings(db, user_id=user_id)
    profile = get_profile(db, user_id=user_id)
    result = {"received": 0, "saved": 0, "duplicates": 0, "filtered_out": 0, "errors": [],
              "candidates": 0, "prepared": 0, "awaiting_approval": 0, "manual_required": 0,
              "sent": 0, "failed": 0, "skipped_daily_limit": 0,
              "profile_gaps": applying.profile_gaps(profile)}

    if collect:
        names = sources or list(SOURCES.keys())
        items, errors = collector(names)
        saved = collect_and_save_ranked(items, limit)
        result.update(received=len(items), saved=saved["saved"], duplicates=saved["duplicates"],
                      filtered_out=saved["filtered_out"], errors=errors)

    if result["profile_gaps"]:
        result["message"] = "Vagas coletadas, mas nenhuma candidatura foi preparada: complete o perfil (" + \
            ", ".join(result["profile_gaps"]) + ")."
        return result

    candidates = pick_candidates(db, settings_row.min_score, user_id=user_id)
    result["candidates"] = len(candidates)
    for job in candidates:
        try:
            attempt = applying.prepare_attempt(db, job, profile)
            if attempt.channel != "email":
                result["manual_required"] += 1
                continue
            if settings_row.require_approval:
                attempt.status, attempt.detail = "awaiting_approval", "Aguardando sua aprovação antes do envio."
                db.commit()
                result["awaiting_approval"] += 1
            elif settings_row.auto_apply_enabled:
                if applying.sent_today_count(db) >= settings_row.daily_limit:
                    attempt.detail = f"Limite diário de {settings_row.daily_limit} atingido; fica na fila."
                    db.commit()
                    result["skipped_daily_limit"] += 1
                    result["prepared"] += 1
                    continue
                applying.send_attempt(db, attempt, settings_row.daily_limit)
                result["sent" if attempt.status == "sent" else "failed"] += 1
            else:
                attempt.detail = "Envio automático desativado; aprove manualmente para enviar."
                db.commit()
                result["prepared"] += 1
        except applying.ApplyError as exc:
            result["errors"].append(f"{job.title}: {exc}")
        except Exception as exc:  # um erro em uma vaga não interrompe as demais
            db.rollback()
            result["errors"].append(f"{job.title}: {type(exc).__name__}: {exc}")
    return result
