"""Preparação e envio de candidaturas.

Regras de integridade:
- Só vira "sent" quando (a) o servidor SMTP aceitou a mensagem ou (b) o próprio usuário confirmou
  explicitamente que enviou. Preparar a candidatura ou abrir o site NUNCA marca como enviada.
- O texto usa apenas dados preenchidos no perfil; nada é inventado.
"""
import html
import re
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from .config import settings
from .matching import normalize, profile_technology_terms
from .models import Application, ApplicationAttempt, Job

OPEN_STATUSES = ("prepared", "awaiting_approval", "manual_required")
SENDABLE_STATUSES = ("prepared", "awaiting_approval", "failed")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
BLOCKED_LOCAL_PARTS = ("noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "privacy", "abuse")


class ApplyError(Exception):
    """Erro de regra de negócio (mostrado ao usuário)."""


# ------------------------------------------------------------------ perfil
def profile_gaps(profile) -> list[str]:
    gaps = []
    if not (profile.name or "").strip():
        gaps.append("nome")
    if not profile_technology_terms(profile):
        gaps.append("tecnologias ou habilidades identificáveis no perfil, projetos ou experiência")
    if not any((getattr(profile, f, "") or "").strip() for f in ("course", "experience", "projects")):
        gaps.append("curso, experiência ou projetos")
    return gaps


def _clip(text, size=500):
    text = " ".join(str(text or "").split())
    return text if len(text) <= size else text[:size].rsplit(" ", 1)[0] + "…"


def matched_profile_terms(job, profile) -> list[str]:
    """Itens do perfil (com a grafia que você cadastrou) que realmente aparecem no texto da vaga."""
    haystack = normalize(f"{job.title} {job.description}")
    found = []
    raw = f"{profile.technologies or ''},{profile.skills or ''}"
    for item in (part.strip() for part in raw.split(",")):
        if item and re.search(r"(?<![a-z0-9+#])" + re.escape(normalize(item)) + r"(?![a-z0-9+#])", haystack):
            if item not in found:
                found.append(item)
    return found


def build_cover_letter(job, profile) -> tuple[str, str]:
    name = profile.name.strip()
    study = []
    if profile.course:
        study.append(profile.course.strip())
    if profile.institution:
        study.append(f"na {profile.institution.strip()}")
    if profile.academic_stage:
        study.append(f"({profile.academic_stage.strip()})")
    lines = ["Prezados(as),", ""]
    intro = f"Meu nome é {name}"
    if study:
        intro += f" e estou cursando {' '.join(study)}" if profile.course else f" ({' '.join(study)})"
    intro += f". Tenho interesse na vaga de {job.title}"
    if job.company and "não informada" not in job.company.lower():
        intro += f" na {job.company}"
    lines.append(intro + ".")
    terms = matched_profile_terms(job, profile)
    if terms:
        lines += ["", "Tenho conhecimentos em " + ", ".join(terms) + ", citados na descrição da vaga."]
    if (profile.projects or "").strip():
        lines += ["", "Projetos: " + _clip(profile.projects)]
    if (profile.experience or "").strip():
        lines += ["", "Experiência: " + _clip(profile.experience)]
    lines += ["", "Agradeço a atenção e fico à disposição para uma conversa.", "", "Atenciosamente,", name]
    return f"Candidatura: {job.title} - {name}", "\n".join(lines)


# --------------------------------------------------------------- conectores
def extract_apply_email(text: str) -> str | None:
    """Primeiro e-mail de contato publicado na descrição da vaga (ignora no-reply e similares)."""
    clean = html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))
    for match in EMAIL_RE.findall(clean):
        local = match.split("@")[0].lower()
        if not any(block in local for block in BLOCKED_LOCAL_PARTS):
            return match
    return None


def email_channel_available(job) -> tuple[bool, str]:
    if not extract_apply_email(job.description):
        return False, "A vaga não publica e-mail de candidatura; finalize no site original."
    if not settings.smtp_can_send_applications:
        return False, "SMTP não configurado no .env (SMTP_HOST, SMTP_FROM, SMTP_USERNAME, SMTP_PASSWORD)."
    return True, ""


def _deliver(msg: EmailMessage):
    """Isolado para facilitar testes. Levanta exceção se o SMTP recusar."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=25) as server:
        server.ehlo()
        if settings.smtp_use_tls:
            server.starttls()
            server.ehlo()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


# ------------------------------------------------------------------ limites
def local_today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def sent_today_count(db, today: date | None = None) -> int:
    """Envios automáticos (e-mail) do dia local. Confirmações manuais não consomem o limite."""
    tz = ZoneInfo(settings.timezone)
    day = today or local_today()
    start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
    end = start + timedelta(days=1)
    return db.scalar(select(func.count(ApplicationAttempt.id)).where(
        ApplicationAttempt.status == "sent", ApplicationAttempt.channel == "email",
        ApplicationAttempt.sent_at >= start, ApplicationAttempt.sent_at < end)) or 0


# ------------------------------------------------------------------ fluxo
def active_attempt(db, job_id):
    return db.scalar(select(ApplicationAttempt).where(
        ApplicationAttempt.job_id == job_id,
        ApplicationAttempt.status.in_(OPEN_STATUSES + ("sent",))).order_by(ApplicationAttempt.id.desc()))


def prepare_attempt(db, job: Job, profile) -> ApplicationAttempt:
    """Monta a candidatura (texto + canal). Não envia nada e não registra como enviada."""
    gaps = profile_gaps(profile)
    if gaps:
        raise ApplyError("Complete seu perfil antes de preparar candidaturas: faltam " + ", ".join(gaps) + ".")
    existing = active_attempt(db, job.id)
    if existing:
        raise ApplyError("Esta vaga já tem uma candidatura em andamento ou enviada.")
    subject, body = build_cover_letter(job, profile)
    ok, reason = email_channel_available(job)
    if ok:
        attempt = ApplicationAttempt(job_id=job.id, status="prepared", channel="email", subject=subject,
                                     message=body, recipient=extract_apply_email(job.description),
                                     detail="Pronta para envio por e-mail.")
    else:
        attempt = ApplicationAttempt(job_id=job.id, status="manual_required", channel="manual", subject=subject,
                                     message=body, detail=reason + f" Link: {job.url}")
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def _ensure_application(db, job_id):
    if not db.scalar(select(Application).where(Application.job_id == job_id)):
        db.add(Application(job_id=job_id, status="Candidatura enviada", applied_at=local_today()))


def send_attempt(db, attempt: ApplicationAttempt, daily_limit: int | None = None) -> ApplicationAttempt:
    """Envia por e-mail. Só marca 'sent' se o SMTP aceitar a mensagem; erros viram 'failed'."""
    if attempt.status not in SENDABLE_STATUSES:
        raise ApplyError(f"Candidatura com status '{attempt.status}' não pode ser enviada.")
    if attempt.channel != "email" or not attempt.recipient:
        raise ApplyError("Esta candidatura não tem canal de envio automático; finalize no site original.")
    if not settings.smtp_can_send_applications:
        raise ApplyError("SMTP não configurado no .env.")
    if daily_limit is not None and sent_today_count(db) >= daily_limit:
        raise ApplyError(f"Limite diário de {daily_limit} candidatura(s) automática(s) atingido.")

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = attempt.subject, settings.smtp_from, attempt.recipient
    msg.set_content(attempt.message)
    if settings.cv_path:
        cv = Path(settings.cv_path)
        if not cv.is_file():
            attempt.status, attempt.detail = "failed", f"CV_PATH aponta para um arquivo inexistente: {cv.name}"
            db.commit()
            return attempt
        msg.add_attachment(cv.read_bytes(), maintype="application", subtype="pdf", filename=cv.name)
    try:
        _deliver(msg)
    except Exception as exc:  # qualquer falha de rede/autenticação: nada é registrado como enviado
        attempt.status, attempt.detail = "failed", f"{type(exc).__name__}: {exc}"
        db.commit()
        return attempt
    attempt.status, attempt.sent_at = "sent", datetime.utcnow()
    attempt.detail = f"E-mail aceito pelo servidor SMTP para {attempt.recipient}."
    _ensure_application(db, attempt.job_id)
    db.commit()
    return attempt


def cancel_attempt(db, attempt):
    if attempt.status == "sent":
        raise ApplyError("Uma candidatura já enviada não pode ser cancelada.")
    attempt.status, attempt.detail = "cancelled", "Cancelada pelo usuário."
    db.commit()
    return attempt


def confirm_manual_send(db, job: Job, note: str = "") -> ApplicationAttempt:
    """O usuário declara que enviou pelo site da vaga. É o único caminho manual para 'sent'."""
    existing = active_attempt(db, job.id)
    if existing and existing.status == "sent":
        raise ApplyError("Esta vaga já consta como enviada.")
    attempt = existing or ApplicationAttempt(job_id=job.id)
    attempt.status, attempt.channel, attempt.sent_at = "sent", "manual_confirmed", datetime.utcnow()
    attempt.detail = "Confirmado manualmente pelo usuário." + (f" {note}" if note else "")
    if attempt.id is None:
        db.add(attempt)
    _ensure_application(db, job.id)
    db.commit()
    db.refresh(attempt)
    return attempt
