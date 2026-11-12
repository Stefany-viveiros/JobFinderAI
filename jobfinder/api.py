from datetime import date, datetime
from email.message import EmailMessage
import hashlib
import secrets
import re
import smtplib
from datetime import timedelta
from pwdlib import PasswordHash
from .models import User, UserSession, PasswordResetToken, AuthRateLimit
from .auth import SESSION_COOKIE, COOKIE_SECURE, create_session, clear_session_cookie
import os
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, or_, case, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session, joinedload, selectinload, aliased

from .db import init_db, SessionLocal, validate_multitenant_schema
from .models import (
    Job, JobMatch, Application, Task, Profile, NotificationLog, ApplicationAttempt,
    Education, Experience, Course, Certification, PortfolioProject,
    MarketAnalysisRun, MarketSkillMetric, MarketSkillPair, Skill, DevelopmentPlanItem, SkillAssessmentAttempt, ApplicationEvent,
    SmtpAccount, UserResume,
)
from .service import get_profile, save_jobs, refresh_scores, create_task, complete_task, STATUSES, collect_and_save_ranked, collect_for_user, refresh_user_scores
from .sources import SOURCES, SOURCE_INFO, LINK_ONLY_SOURCES, collect_selected, external_search_links
from . import applying
from .agent import get_agent_settings, run_agent, TARGET_LEVELS
from .mailer import send_daily_reminder
from .config import settings, parse_cors_origins
from .smtp_credentials import encrypt_password, decrypt_password, CredentialEncryptionError
from .resume_parser import parse_resume, extract_resume_text
from .resume_ai import analyze_resume_with_gemini, ResumeAIError
from .resume_storage import encrypt_resume, safe_filename, resume_content_type, ResumeStorageError
from .market_service import (create_market_snapshot, index_unprocessed_jobs, build_profile_gap,
    list_development_plan, create_development_item, update_development_item, DEVELOPMENT_STATUSES,
    create_skill_assessment, submit_skill_assessment, list_skill_assessments, compare_market_trends)
from .career_twin import build_career_twin
from .evidence_ledger import sync_profile_evidence, list_profile_evidence, record_self_assessment_evidence, review_profile_evidence, list_evidence_reviews, list_dismissed_evidence_keys
from .matching import diagnose_job_requirements

app = FastAPI(title="JobFinder AI API", version="1.1.0", description="API do JobFinder AI")
try:
    cors_origins = parse_cors_origins(
        os.getenv("CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173"
    )
except ValueError as exc:
    raise RuntimeError(f"Configuração CORS insegura: {exc}") from exc
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Token"],
)

@app.middleware("http")
async def demo_read_only_guard(request, call_next):
    """Bloqueia mutações no ambiente público de demonstração."""
    read_only = os.getenv("DEMO_READ_ONLY", "false").lower() == "true"
    if read_only and request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=403,
            content={"detail": "Ambiente de demonstração: alterações estão desativadas."},
        )
    return await call_next(request)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



@app.middleware("http")
async def require_authenticated_session(request, call_next):
    """Protege a API inteira; somente health e endpoints de autenticação são públicos."""
    path = request.url.path
    public_paths = {
        "/api/health", "/api/auth/register", "/api/auth/login",
        "/api/auth/forgot-password", "/api/auth/reset-password",
    }
    if not path.startswith("/api/") or path in public_paths or path == "/api/auth/me":
        return await call_next(request)
    # Fail closed: endpoints legados ainda estão sendo convertidos para consultas
    # com escopo por usuário. Não exponha dados globais a contas autenticadas.
    if os.getenv("MULTITENANT_READY", "false").lower() != "true":
        return JSONResponse(
            status_code=503,
            content={"detail": "A área da aplicação está em implantação. O acesso será liberado após a conclusão do isolamento entre contas."},
        )
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return JSONResponse(status_code=401, content={"detail": "Faça login para continuar."})
    db = SessionLocal()
    try:
        session = db.scalar(select(UserSession).where(
            UserSession.token_hash == _token_hash(raw),
            UserSession.expires_at > datetime.utcnow(),
        ))
        if not session or not session.user.is_active:
            return JSONResponse(status_code=401, content={"detail": "Sessão inválida ou expirada."})
        request.state.user_id = session.user_id
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            if not supplied or not secrets.compare_digest(supplied, session.csrf_token):
                return JSONResponse(status_code=403, content={"detail": "Validação CSRF inválida."})
    finally:
        db.close()
    return await call_next(request)


@app.on_event("startup")
def startup():
    init_db()
    if os.getenv('MULTITENANT_READY', 'false').lower() == 'true':
        validate_multitenant_schema()
    # Perfis individuais são criados sob demanda após autenticação.



class RegisterInput(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=12, max_length=128)


class LoginInput(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordInput(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class ResetPasswordInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=128)


password_hasher = PasswordHash.recommended()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _enforce_rate_limit(
    db: Session, request: Request, *, scope: str, subject: str,
    limit: int, window_seconds: int,
) -> None:
    """Aplica limite persistente e atômico por janela, compatível com SQLite/PostgreSQL."""
    client_host = request.client.host if request.client else "unknown"
    # Contas/e-mails/tokens precisam de uma janela global por identidade,
    # independente do IP usado. Limites explicitamente por IP continuam separados.
    subject_scopes = (
        scope.endswith("-user")
        or scope.endswith("-email")
        or scope == "auth-reset-token"
    )
    identity = str(subject) if subject_scopes else f"{client_host}|{subject}"
    key = _token_hash(f"{scope}|{identity}")
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    # Todos os limites deste módulo expiram em até 1 hora. Remove buckets
    # inativos há 48 horas para impedir crescimento indefinido da tabela.
    db.execute(delete(AuthRateLimit).where(
        AuthRateLimit.window_started_at < now - timedelta(hours=48)
    ))
    dialect = db.get_bind().dialect.name
    values = {
        "bucket_key": key,
        "window_started_at": now,
        "attempts": 1,
    }
    if dialect == "sqlite":
        statement = sqlite_insert(AuthRateLimit).values(**values)
    elif dialect == "postgresql":
        statement = postgresql_insert(AuthRateLimit).values(**values)
    else:
        raise RuntimeError("Banco não suportado para controle de requisições.")

    expired_window = AuthRateLimit.window_started_at <= cutoff
    statement = statement.on_conflict_do_update(
        index_elements=[AuthRateLimit.bucket_key],
        set_={
            "attempts": case(
                (expired_window, 1),
                else_=AuthRateLimit.attempts + 1,
            ),
            "window_started_at": case(
                (expired_window, now),
                else_=AuthRateLimit.window_started_at,
            ),
        },
    ).returning(AuthRateLimit.attempts, AuthRateLimit.window_started_at)

    attempts, window_started = db.execute(statement).one()
    db.commit()
    if attempts > limit:
        retry_after = max(
            1,
            int((window_started + timedelta(seconds=window_seconds) - now).total_seconds()),
        )
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Aguarde antes de tentar novamente.",
            headers={"Retry-After": str(retry_after)},
        )


def _public_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@app.post("/api/auth/register")
def register(payload: RegisterInput, request: Request, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip()
    normalized = email.casefold()
    _enforce_rate_limit(db, request, scope="auth-register-ip", subject="all", limit=5, window_seconds=3600)
    if db.scalar(select(User).where(User.email_normalized == normalized)):
        raise HTTPException(409, "Já existe uma conta com esse e-mail.")
    user = User(
        email=email, email_normalized=normalized, full_name=payload.full_name.strip(),
        password_hash=password_hasher.hash(payload.password), role="user", is_active=True,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(409, "Não foi possível criar a conta. Verifique se o e-mail já está cadastrado.")
    create_session(response, db, user)
    return {"user": _public_user(user)}


@app.post("/api/auth/login")
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().casefold()
    _enforce_rate_limit(db, request, scope="auth-login-ip", subject="all", limit=30, window_seconds=900)
    _enforce_rate_limit(db, request, scope="auth-login-email", subject=normalized_email, limit=10, window_seconds=900)
    user = db.scalar(select(User).where(User.email_normalized == normalized_email))
    if not user or not user.is_active or not password_hasher.verify(payload.password, user.password_hash):
        raise HTTPException(401, "E-mail ou senha inválidos.")
    create_session(response, db, user)
    return {"user": _public_user(user)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(raw)))
        if session:
            db.delete(session)
            db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request, db: Session = Depends(get_db)):
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(401, "Faça login para continuar.")
    session = db.scalar(select(UserSession).where(
        UserSession.token_hash == _token_hash(raw), UserSession.expires_at > datetime.utcnow()
    ))
    if not session or not session.user.is_active:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    response = JSONResponse({"user": _public_user(session.user), "csrf_token": session.csrf_token})
    return response


@app.post("/api/auth/forgot-password")
def forgot_password(payload: ForgotPasswordInput, request: Request, db: Session = Depends(get_db)):
    # Resposta idêntica exista ou não a conta, para não revelar cadastros.
    normalized_email = payload.email.strip().casefold()
    _enforce_rate_limit(db, request, scope="auth-forgot-ip", subject="all", limit=10, window_seconds=3600)
    _enforce_rate_limit(db, request, scope="auth-forgot-email", subject=normalized_email, limit=3, window_seconds=3600)
    user = db.scalar(select(User).where(User.email_normalized == normalized_email))
    if user:
        raw_token = secrets.token_urlsafe(40)
        reset = PasswordResetToken(
            user_id=user.id, token_hash=_token_hash(raw_token),
            expires_at=datetime.utcnow() + timedelta(minutes=30),
        )
        db.add(reset)
        db.commit()
        base_url = os.getenv("APP_BASE_URL", "").rstrip("/")
        if settings.smtp_host and settings.smtp_from and settings.smtp_username and settings.smtp_password and base_url:
            message = EmailMessage()
            message["Subject"] = "Redefinição de senha — JobFinder AI"
            message["From"] = settings.smtp_from
            message["To"] = user.email
            message.set_content(
                "Recebemos uma solicitação para redefinir sua senha. "
                "Use o link abaixo em até 30 minutos:\n\n"
                + base_url + "/redefinir-senha?token=" + raw_token
                + "\n\nSe não foi você, ignore este e-mail."
            )
            try:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                    server.ehlo()
                    if settings.smtp_use_tls:
                        server.starttls()
                        server.ehlo()
                    server.login(settings.smtp_username, settings.smtp_password)
                    server.send_message(message)
            except Exception:
                # Não expõe token nem detalhes SMTP ao cliente.
                db.rollback()
    return {"message": "Se o e-mail estiver cadastrado, você receberá instruções para redefinir a senha."}


@app.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordInput, request: Request, db: Session = Depends(get_db)):
    _enforce_rate_limit(db, request, scope="auth-reset-ip", subject="all", limit=10, window_seconds=3600)
    _enforce_rate_limit(db, request, scope="auth-reset-token", subject=_token_hash(payload.token), limit=5, window_seconds=3600)
    reset = db.scalar(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == _token_hash(payload.token),
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.utcnow(),
    ))
    if not reset:
        raise HTTPException(400, "Link inválido ou expirado. Solicite uma nova redefinição.")
    user = db.get(User, reset.user_id)
    if not user or not user.is_active:
        raise HTTPException(400, "Não foi possível redefinir a senha.")
    now = datetime.utcnow()
    user.password_hash = password_hasher.hash(payload.password)
    # Uma redefinição bem-sucedida invalida todos os links pendentes da conta,
    # não apenas o token utilizado nesta requisição.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update(
        {PasswordResetToken.used_at: now},
        synchronize_session=False,
    )
    # Invalida todas as sessões existentes após a troca da senha.
    db.query(UserSession).filter(UserSession.user_id == user.id).delete()
    db.commit()
    return {"message": "Senha redefinida. Faça login novamente."}


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company: str = "Empresa não informada"
    url: str = Field(min_length=1)
    location: str = "Não informada"
    description: str = ""
    modality: str = "Não informada"
    job_type: str = "Não informado"
    published_at: str = ""


class ApplicationUpdate(BaseModel):
    status: str = "Candidatura enviada"
    applied_at: Optional[date] = None
    deadline: Optional[date] = None
    recruiter: str = ""
    notes: str = ""


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    due_date: Optional[date] = None
    priority: str = "Média"
    job_id: Optional[int] = None
    notify: bool = True


class TaskUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    due_date: Optional[date] = None
    priority: str = "Média"
    status: str = "Pendente"
    notify: bool = True


class EducationInput(BaseModel):
    id: Optional[int] = None
    course: str = Field("", max_length=200)
    institution: str = Field("", max_length=200)
    degree: str = Field("", max_length=80)
    status: str = Field("Em andamento", max_length=40)
    start_date: str = Field("", max_length=30)
    end_date: str = Field("", max_length=30)
    description: str = ""


class ExperienceInput(BaseModel):
    id: Optional[int] = None
    company: str = Field("", max_length=200)
    role: str = Field("", max_length=160)
    employment_type: str = Field("", max_length=60)
    location: str = Field("", max_length=160)
    start_date: str = Field("", max_length=30)
    end_date: str = Field("", max_length=30)
    is_current: bool = False
    description: str = ""


class CourseInput(BaseModel):
    id: Optional[int] = None
    name: str = Field("", max_length=220)
    provider: str = Field("", max_length=180)
    workload: str = Field("", max_length=40)
    completed_at: str = Field("", max_length=30)
    status: str = Field("Concluído", max_length=40)
    credential_url: str = ""


class CertificationInput(BaseModel):
    id: Optional[int] = None
    name: str = Field("", max_length=220)
    issuer: str = Field("", max_length=180)
    issued_at: str = Field("", max_length=30)
    expires_at: str = Field("", max_length=30)
    credential_id: str = Field("", max_length=160)
    credential_url: str = ""


class PortfolioProjectInput(BaseModel):
    id: Optional[int] = None
    name: str = Field("", max_length=220)
    description: str = ""
    technologies: str = ""
    repository_url: str = ""
    demo_url: str = ""
    status: str = Field("Em desenvolvimento", max_length=40)


class ProfileUpdate(BaseModel):
    name: str = ""
    course: str = ""
    institution: str = ""
    academic_stage: str = ""
    technologies: str = ""
    skills: str = ""
    experience: str = ""
    projects: str = ""
    certifications: str = ""
    keywords: str = ""
    interests: str = "Estágio em Tecnologia"
    location: str = ""
    modality: str = "Remoto, Híbrido, Presencial"
    job_types: str = "Estágio, Júnior"
    exclude_terms: str = ""
    weight_keywords: int = 40
    weight_area: int = 25
    weight_modality: int = 15
    weight_location: int = 10
    weight_level: int = 10
    educations: Optional[list[EducationInput]] = None
    experiences: Optional[list[ExperienceInput]] = None
    courses: Optional[list[CourseInput]] = None
    certifications_items: Optional[list[CertificationInput]] = None
    portfolio_projects: Optional[list[PortfolioProjectInput]] = None


def job_dict(j: Job, with_application=True, db=None, user_id=None):
    match = db.scalar(select(JobMatch).where(JobMatch.job_id == j.id, JobMatch.user_id == user_id)) if db is not None and user_id is not None else None
    app_row = db.scalar(select(Application).where(Application.job_id == j.id, Application.user_id == user_id)) if with_application and db is not None and user_id is not None else None
    latest_attempt = db.scalar(select(ApplicationAttempt).where(ApplicationAttempt.job_id == j.id, ApplicationAttempt.user_id == user_id).order_by(ApplicationAttempt.id.desc())) if db is not None and user_id is not None else None
    application = None
    if app_row:
        application = {"id": app_row.id, "status": app_row.status,
            "applied_at": app_row.applied_at.isoformat() if app_row.applied_at else None,
            "deadline": app_row.deadline.isoformat() if app_row.deadline else None,
            "recruiter": app_row.recruiter or "", "notes": app_row.notes or ""}
    return {"id": j.id, "source": j.source, "source_id": j.source_id,
        "title": j.title, "company": j.company, "description": j.description or "",
        "location": j.location, "modality": j.modality, "job_type": j.job_type,
        "published_at": j.published_at or "", "url": j.url,
        "compatibility": round(match.compatibility or 0) if match else 0,
        "match_reasons": match.match_reasons or "" if match else "",
        "missing_reasons": match.missing_reasons or "" if match else "",
        "is_favorite": bool(match.is_favorite) if match else False,
        "is_archived": bool(match.is_archived) if match else False,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "level": j.level or "", "application": application,
        "latest_attempt": attempt_dict(latest_attempt) if latest_attempt else None}

def attempt_dict(a: ApplicationAttempt, with_message=False):
    data = {
        "id": a.id, "job_id": a.job_id, "status": a.status, "channel": a.channel,
        "recipient": a.recipient or "", "subject": a.subject or "", "detail": a.detail or "",
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "sent_at": a.sent_at.isoformat() if a.sent_at else None,
    }
    if with_message:
        data["message"] = a.message or ""
    return data


def task_dict(t: Task):
    return {
        "id": t.id, "job_id": t.job_id, "job_title": t.job.title if t.job else None,
        "title": t.title, "description": t.description or "",
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "priority": t.priority, "status": t.status, "notify": bool(t.notify),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


def profile_dict(p: Profile):
    def records(items, fields):
        return [{key: getattr(item, key) for key in ("id", *fields)} for item in items]

    return {k: getattr(p, k) for k in [
        "id", "name", "course", "institution", "academic_stage", "technologies", "skills",
        "experience", "projects", "certifications", "keywords", "interests", "location",
        "modality", "job_types", "exclude_terms", "weight_keywords", "weight_area",
        "weight_modality", "weight_location", "weight_level"
    ]} | {
        "educations": records(p.educations, ("course", "institution", "degree", "status", "start_date", "end_date", "description")),
        "experiences": records(p.experiences, ("company", "role", "employment_type", "location", "start_date", "end_date", "is_current", "description")),
        "courses": records(p.courses, ("name", "provider", "workload", "completed_at", "status", "credential_url")),
        "certifications_items": records(p.certifications_items, ("name", "issuer", "issued_at", "expires_at", "credential_id", "credential_url")),
        "portfolio_projects": records(p.portfolio_projects, ("name", "description", "technologies", "repository_url", "demo_url", "status")),
    }


def _sync_profile_records(existing, incoming, model, fields):
    current = {item.id: item for item in existing}
    retained = []
    for payload in incoming:
        if isinstance(payload, BaseModel):
            item_id = payload.id
            data = payload.model_dump(exclude={"id"})
        else:
            item_id = payload.get("id")
            data = {key: value for key, value in payload.items() if key != "id"}
        data = {key: (value.strip() if isinstance(value, str) else value) for key, value in data.items()}
        if not any(value for value in data.values()):
            continue
        item = current.pop(item_id, None) if item_id is not None else None
        if item is None:
            item = model(**data)
        else:
            for key, value in data.items():
                setattr(item, key, value)
        retained.append(item)
    existing[:] = retained


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "JobFinder AI"}


def count_attempts_channel(db, channel, user_id=None):
    stmt = select(func.count(func.distinct(ApplicationAttempt.job_id))).where(
        ApplicationAttempt.status == "sent", ApplicationAttempt.channel == channel)
    if user_id is not None:
        stmt = stmt.where(ApplicationAttempt.user_id == user_id)
    return db.scalar(stmt) or 0


@app.get("/api/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.state.user_id
    match_filter = select(JobMatch.job_id).where(JobMatch.user_id == user_id, JobMatch.is_archived.is_(False))
    total = db.scalar(select(func.count(Job.id)).where(Job.id.in_(match_filter))) or 0
    new = db.scalar(select(func.count(Job.id)).where(Job.id.in_(match_filter), ~Job.id.in_(select(Application.job_id).where(Application.user_id == user_id)))) or 0
    saved = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.user_id == user_id, JobMatch.is_favorite.is_(True), JobMatch.is_archived.is_(False))) or 0
    apps = db.scalar(select(func.count(Application.id)).where(Application.user_id == user_id)) or 0
    interviews = db.scalar(select(func.count(Application.id)).where(Application.user_id == user_id, Application.status == "Entrevista")) or 0
    pending = db.scalar(select(func.count(Task.id)).where(Task.user_id == user_id, Task.status != "Concluída")) or 0
    overdue = db.scalar(select(func.count(Task.id)).where(Task.user_id == user_id, Task.status != "Concluída", Task.due_date < date.today())) or 0
    avg_score = db.scalar(select(func.avg(JobMatch.compatibility)).where(JobMatch.user_id == user_id, JobMatch.is_archived.is_(False))) or 0
    upcoming = db.scalars(select(Task).options(joinedload(Task.job)).where(
        Task.user_id == user_id, Task.status != "Concluída", Task.due_date.is_not(None)
    ).order_by(Task.due_date).limit(6)).all()
    recent_jobs = db.scalars(select(Job).join(JobMatch, JobMatch.job_id == Job.id).where(
        JobMatch.user_id == user_id, JobMatch.is_archived.is_(False)
    ).order_by(Job.created_at.desc()).limit(5)).all()
    p = get_profile(db, user_id)
    agent = get_agent_settings(db, user_id=user_id)
    count_attempts = lambda *statuses: db.scalar(select(func.count(func.distinct(ApplicationAttempt.job_id))).where(
        ApplicationAttempt.user_id == user_id, ApplicationAttempt.status.in_(statuses))) or 0
    compatible = db.scalar(select(func.count(JobMatch.id)).join(Job, Job.id == JobMatch.job_id).where(
        JobMatch.user_id == user_id, JobMatch.is_archived.is_(False), Job.level.in_(TARGET_LEVELS), JobMatch.compatibility >= agent.min_score)) or 0
    target_jobs = db.scalar(select(func.count(JobMatch.id)).join(Job, Job.id == JobMatch.job_id).where(
        JobMatch.user_id == user_id, JobMatch.is_archived.is_(False), Job.level.in_(TARGET_LEVELS))) or 0
    return {
        "metrics": {"total_jobs": total, "new_jobs": new, "favorites": saved,
                    "applications": apps, "interviews": interviews, "pending_tasks": pending,
                    "overdue_tasks": overdue, "average_compatibility": round(avg_score),
                    "target_jobs": target_jobs, "compatible_jobs": compatible,
                    "min_score": agent.min_score,
                    "sent_applications": count_attempts("sent"),
                    "sent_automatically": count_attempts_channel(db, "email", user_id),
                    "sent_manually_confirmed": count_attempts_channel(db, "manual_confirmed", user_id),
                    "pending_applications": count_attempts("prepared", "awaiting_approval", "manual_required"),
                    "awaiting_approval": count_attempts("awaiting_approval"),
                    "failed_applications": count_attempts("failed")},
        "upcoming_tasks": [task_dict(t) for t in upcoming],
        "recent_jobs": [job_dict(j, db=db, user_id=user_id) for j in recent_jobs],
        "profile_name": p.name,
        # Lembretes usam o destinatário administrativo local; candidaturas usam SMTP individual.
        "smtp_ready": bool(settings.smtp_ready and settings.smtp_username and settings.smtp_password),
    }


@app.get("/api/jobs")
def list_jobs(
    request: Request,
    q: str = "", min_score: int = Query(0, ge=0, le=100), favorite: bool = False,
    modality: str = "Todas", sort: str = "Compatibilidade", only_new: bool = False,
    level: str = "todas", source: str = "Todas", attempt_status: str = "todas",
    limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)
):
    user_id = request.state.user_id
    stmt = select(Job).join(JobMatch, JobMatch.job_id == Job.id).where(
        JobMatch.user_id == user_id, JobMatch.is_archived.is_(False), JobMatch.compatibility >= min_score)
    if level == "alvo":
        stmt = stmt.where(Job.level.in_(TARGET_LEVELS))
    elif level in ("estagio", "junior", "outro"):
        stmt = stmt.where(Job.level == level)
    if source != "Todas":
        stmt = stmt.where(Job.source == source)
    if attempt_status == "sem_tentativa":
        stmt = stmt.where(~Job.id.in_(select(ApplicationAttempt.job_id).where(ApplicationAttempt.user_id == user_id)))
    elif attempt_status != "todas":
        stmt = stmt.where(Job.id.in_(select(ApplicationAttempt.job_id).where(ApplicationAttempt.user_id == user_id, ApplicationAttempt.status == attempt_status)))
    if favorite:
        stmt = stmt.where(JobMatch.is_favorite.is_(True))
    if modality != "Todas":
        stmt = stmt.where(Job.modality.ilike(f"%{modality}%"))
    if q.strip():
        search = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(search), Job.company.ilike(search), Job.description.ilike(search)))
    if only_new:
        stmt = stmt.where(~Job.id.in_(select(Application.job_id).where(Application.user_id == user_id)))
    stmt = stmt.order_by(JobMatch.compatibility.desc() if sort == "Compatibilidade" else Job.created_at.desc()).limit(limit)
    return [job_dict(j, db=db, user_id=user_id) for j in db.scalars(stmt).unique().all()]


@app.post("/api/jobs")
def create_job(payload: JobCreate, request: Request, db: Session = Depends(get_db)):
    url = payload.url.strip()
    if not url:
        raise HTTPException(400, "Informe o link original da vaga.")
    item = payload.model_dump()
    item.update({"source": "Manual", "source_id": None, "published_at": payload.published_at})
    result = collect_for_user(db, [item], user_id=request.state.user_id, limit=1, only_target=False)
    existing = db.scalar(select(Job).where(Job.url == url))
    if not existing:
        raise HTTPException(400, "Não foi possível salvar a vaga.")
    message = (
        "Link já cadastrado."
        if result["duplicates"]
        else "Vaga salva ou atualizada no seu painel."
    )
    return {"message": message, "job": job_dict(existing, db=db, user_id=request.state.user_id)}




@app.get("/api/jobs/{job_id}/diagnosis")
def diagnose_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    """Diagnóstico de requisitos restrito às vagas que pertencem ao painel da conta."""
    user_id = request.state.user_id
    row = db.execute(
        select(Job, JobMatch)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .where(Job.id == job_id, JobMatch.user_id == user_id, JobMatch.is_archived.is_(False))
    ).first()
    if row is None:
        raise HTTPException(404, "Oportunidade não encontrada no seu painel.")
    job, match = row
    profile = get_profile(db, user_id)
    dismissed_evidence = list_dismissed_evidence_keys(db, user_id=user_id)
    assessment_rows = db.execute(
        select(SkillAssessmentAttempt.id, Skill.canonical_name)
        .join(Skill, SkillAssessmentAttempt.skill_id == Skill.id)
        .where(
            SkillAssessmentAttempt.user_id == user_id,
            SkillAssessmentAttempt.status == "self_reviewed",
        )
    ).all()
    assessed_names = {
        name for attempt_id, name in assessment_rows
        if (f"challenge_attempt:{attempt_id}", name) not in dismissed_evidence
    }
    diagnosis = diagnose_job_requirements(
        job.description or "",
        profile,
        self_assessed_skill_names=assessed_names,
        dismissed_evidence_keys=dismissed_evidence,
    )
    return {
        "job": {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "level": job.level,
            "source": job.source,
        },
        "compatibility": {
            "score": round(match.compatibility or 0),
            "label": "Triagem heurística explicável; não representa probabilidade de contratação.",
            "matched": [x for x in (match.match_reasons or "").split("\\n") if x],
            "to_review": [x for x in (match.missing_reasons or "").split("\\n") if x],
        },
        **diagnosis,
    }

@app.post("/api/jobs/collect")
def collect_jobs(payload: dict, request: Request, db: Session = Depends(get_db)):
    names = payload.get("sources") or list(SOURCES.keys())
    link_only = [n for n in names if n in LINK_ONLY_SOURCES]
    if link_only:
        raise HTTPException(400, f"{', '.join(link_only)} não tem integração automática permitida; use os links de busca e cadastre a vaga manualmente.")
    invalid = [n for n in names if n not in SOURCES]
    if invalid:
        raise HTTPException(400, f"Fontes desconhecidas: {', '.join(invalid)}")

    try:
        limit = int(payload.get("limit", 80))
    except (TypeError, ValueError):
        raise HTTPException(400, "O limite deve ser um número entre 1 e 80.")

    if limit < 1 or limit > 80:
        raise HTTPException(400, "O limite deve ser um número entre 1 e 80.")

    items, errors = collect_selected(names)
    result = collect_for_user(db, items, user_id=request.state.user_id, limit=limit, only_target=bool(payload.get("only_target", True)))

    return {
        "received": len(items),
        "saved": result["saved"],
        "duplicates": result["duplicates"],
        "eligible": result["eligible"],
        "filtered_out": result["filtered_out"],
        "limit": result["limit"],
        "highest_compatibility": result["highest_compatibility"],
        "errors": errors,
    }


def _require_user_job_match(db: Session, job_id: int, user_id: int) -> JobMatch:
    """Exige que a oportunidade esteja vinculada e ativa no painel da conta."""
    match = db.scalar(select(JobMatch).where(
        JobMatch.job_id == job_id,
        JobMatch.user_id == user_id,
        JobMatch.is_archived.is_(False),
    ))
    if match is None:
        raise HTTPException(404, "Oportunidade não encontrada no seu painel.")
    return match


@app.patch("/api/jobs/{job_id}/favorite")
def toggle_favorite(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    match = _require_user_job_match(db, job_id, request.state.user_id)
    match.is_favorite = not match.is_favorite
    db.commit()
    return {"id": job.id, "is_favorite": match.is_favorite}


class ConfirmSent(BaseModel):
    confirmed: bool = False
    note: str = ""


@app.post("/api/jobs/{job_id}/apply")
def apply_to_job(job_id: int, payload: ConfirmSent, request: Request, db: Session = Depends(get_db)):
    """Registra candidatura feita MANUALMENTE pelo usuário. Exige confirmed=true: abrir a vaga ou
    preparar o texto não conta como envio."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    _require_user_job_match(db, job_id, request.state.user_id)
    if not payload.confirmed:
        raise HTTPException(400, "Confirme que você já enviou a candidatura no site da vaga.")
    try:
        attempt = applying.confirm_manual_send(db, job, payload.note, user_id=request.state.user_id)
    except applying.ApplyError as exc:
        raise HTTPException(409, str(exc))
    app_row = db.scalar(select(Application).where(Application.job_id == job.id, Application.user_id == request.state.user_id))
    return {"message": "Candidatura registrada como enviada (confirmação manual).",
            "application_id": app_row.id if app_row else None, "attempt": attempt_dict(attempt)}


@app.post("/api/jobs/{job_id}/prepare")
def prepare_job_application(job_id: int, request: Request, db: Session = Depends(get_db)):
    """Prepara o texto e define o canal. Não envia e não marca como enviada."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    _require_user_job_match(db, job_id, request.state.user_id)
    try:
        attempt = applying.prepare_attempt(db, job, get_profile(db, request.state.user_id), user_id=request.state.user_id)
    except applying.ApplyError as exc:
        raise HTTPException(400, str(exc))
    msg = ("Candidatura preparada. Revise e aprove o envio." if attempt.channel == "email"
           else "Candidatura preparada. Abra a vaga, finalize no site e confirme o envio manualmente.")
    return {"message": msg, "attempt": attempt_dict(attempt, with_message=True)}


@app.get("/api/attempts")
def list_attempts(request: Request, status: str = "todas", limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db)):
    user_id = request.state.user_id
    # Compatibilidade e lacunas são privadas: nunca ler os campos legados globais de Job.
    stmt = (
        select(ApplicationAttempt, JobMatch)
        .outerjoin(
            JobMatch,
            (JobMatch.job_id == ApplicationAttempt.job_id)
            & (JobMatch.user_id == ApplicationAttempt.user_id),
        )
        .options(joinedload(ApplicationAttempt.job))
        .where(ApplicationAttempt.user_id == user_id)
        .order_by(ApplicationAttempt.id.desc())
        .limit(limit)
    )
    if status != "todas":
        stmt = stmt.where(ApplicationAttempt.status == status)
    rows = db.execute(stmt).all()
    return [{
        **attempt_dict(attempt, with_message=True),
        "job": {
            "id": attempt.job.id,
            "title": attempt.job.title,
            "company": attempt.job.company,
            "url": attempt.job.url,
            "compatibility": round(match.compatibility or 0) if match else 0,
            "source": attempt.job.source,
            "missing_reasons": (match.missing_reasons or "") if match else "",
        },
    } for attempt, match in rows]


def _attempt_or_404(db, attempt_id, user_id):
    attempt = db.scalar(select(ApplicationAttempt).where(ApplicationAttempt.id == attempt_id, ApplicationAttempt.user_id == user_id))
    if not attempt:
        raise HTTPException(404, "Tentativa de candidatura não encontrada.")
    return attempt


@app.post("/api/attempts/{attempt_id}/approve")
def approve_attempt(attempt_id: int, request: Request, db: Session = Depends(get_db)):
    """Aprova e envia por e-mail. O status final reflete o resultado real do envio."""
    attempt = _attempt_or_404(db, attempt_id, request.state.user_id)
    agent_settings = get_agent_settings(db, user_id=request.state.user_id)
    match = db.scalar(select(JobMatch).where(
        JobMatch.user_id == request.state.user_id,
        JobMatch.job_id == attempt.job_id,
    ))
    compatibility = match.compatibility if match else 0
    missing_reasons = match.missing_reasons if match else ""
    if compatibility < agent_settings.min_score:
        raise HTTPException(
            409,
            f"Compatibilidade atual ({round(compatibility)}%) abaixo do mínimo configurado "
            f"({agent_settings.min_score}%). Revise a vaga antes de aprovar."
        )
    if "Requisito(s) obrigatório(s) não identificado(s)" in (missing_reasons or ""):
        raise HTTPException(
            409,
            "Há requisito(s) obrigatório(s) que ainda não foram identificados no seu perfil. "
            "Revise a vaga e confirme sua compatibilidade antes de aprovar."
        )
    limit = agent_settings.daily_limit
    try:
        applying.send_attempt(db, attempt, limit, user_id=request.state.user_id)
    except applying.ApplyError as exc:
        raise HTTPException(400, str(exc))
    message = "Candidatura enviada." if attempt.status == "sent" else f"O envio falhou: {attempt.detail}"
    return {"message": message, "attempt": attempt_dict(attempt)}


@app.post("/api/attempts/{attempt_id}/cancel")
def cancel_attempt(attempt_id: int, request: Request, db: Session = Depends(get_db)):
    attempt = _attempt_or_404(db, attempt_id, request.state.user_id)
    try:
        applying.cancel_attempt(db, attempt)
    except applying.ApplyError as exc:
        raise HTTPException(409, str(exc))
    return {"message": "Candidatura cancelada.", "attempt": attempt_dict(attempt)}


class SmtpAccountUpdate(BaseModel):
    host: str = Field(..., min_length=3, max_length=255)
    port: int = Field(587, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=4096)
    from_email: str = Field(..., min_length=3, max_length=320)
    use_tls: bool = True


def smtp_account_dict(account):
    if account is None:
        return {"configured": False}
    try:
        decrypt_password(account.encrypted_password)
        ready = True
    except CredentialEncryptionError:
        ready = False
    return {
        "configured": True,
        "ready": ready,
        "host": account.host,
        "port": account.port,
        "username": account.username,
        "from_email": account.from_email,
        "use_tls": account.use_tls,
    }


@app.get("/api/agent/smtp")
def read_smtp_account(request: Request, db: Session = Depends(get_db)):
    account = db.scalar(select(SmtpAccount).where(SmtpAccount.user_id == request.state.user_id))
    return smtp_account_dict(account)


@app.put("/api/agent/smtp")
def save_smtp_account(payload: SmtpAccountUpdate, request: Request, db: Session = Depends(get_db)):
    host = payload.host.strip()
    sender = payload.from_email.strip()
    if not host or any(char.isspace() for char in host) or "://" in host or "/" in host:
        raise HTTPException(422, "Informe somente o hostname do servidor SMTP, sem protocolo ou caminho.")
    allowed_smtp_hosts = {
        "smtp.gmail.com", "smtp.office365.com", "smtp-mail.outlook.com",
        "smtp.mail.yahoo.com", "smtp.zoho.com", "smtp.zoho.eu",
    }
    allowed_smtp_hosts.update(
        item.strip().lower()
        for item in os.getenv("SMTP_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    )
    if host.lower() not in allowed_smtp_hosts:
        raise HTTPException(
            422,
            "Servidor SMTP não permitido. Use um provedor suportado ou solicite a inclusão "
            "do hostname em SMTP_ALLOWED_HOSTS pelo administrador.",
        )
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", sender):
        raise HTTPException(422, "Endereço de remetente inválido.")
    try:
        encrypted = encrypt_password(payload.password)
    except CredentialEncryptionError as exc:
        raise HTTPException(503, str(exc))
    account = db.scalar(select(SmtpAccount).where(SmtpAccount.user_id == request.state.user_id))
    if account is None:
        account = SmtpAccount(user_id=request.state.user_id)
        db.add(account)
    account.host = host
    account.port = payload.port
    account.username = payload.username.strip()
    account.encrypted_password = encrypted
    account.from_email = sender
    account.use_tls = payload.use_tls
    db.commit()
    db.refresh(account)
    return {"message": "Conexão SMTP individual salva com senha cifrada.", "smtp": smtp_account_dict(account)}


@app.delete("/api/agent/smtp")
def delete_smtp_account(request: Request, db: Session = Depends(get_db)):
    account = db.scalar(select(SmtpAccount).where(SmtpAccount.user_id == request.state.user_id))
    if account is not None:
        db.delete(account)
        db.commit()
    return {"message": "Conexão SMTP individual removida.", "smtp": {"configured": False}}


class AgentSettingsUpdate(BaseModel):
    auto_apply_enabled: bool = False
    require_approval: bool = True
    daily_limit: int = Field(5, ge=0, le=50)
    min_score: int = Field(80, ge=0, le=100)


def agent_settings_dict(db, user_id=None):
    s = get_agent_settings(db, user_id=user_id)
    p = get_profile(db, user_id=user_id)
    smtp_account = db.scalar(select(SmtpAccount).where(SmtpAccount.user_id == user_id))
    return {"auto_apply_enabled": s.auto_apply_enabled, "require_approval": s.require_approval,
            "daily_limit": s.daily_limit, "min_score": s.min_score,
            "sent_today": applying.sent_today_count(db, user_id=user_id),
            "email_ready": bool(smtp_account_dict(smtp_account).get("ready", False)) and
                           os.getenv("MULTITENANT_READY", "false").strip().lower() != "true",
            "email_block_reason": (
                "O envio por e-mail ficará disponível quando o currículo individual puder ser armazenado "
                "e anexado com segurança. Até lá, finalize no portal original."
                if os.getenv("MULTITENANT_READY", "false").strip().lower() == "true" else ""
            ),
            "profile_gaps": applying.profile_gaps(p), "profile_ready": not applying.profile_gaps(p)}


@app.get("/api/agent/settings")
def read_agent_settings(request: Request, db: Session = Depends(get_db)):
    return agent_settings_dict(db, request.state.user_id)


@app.put("/api/agent/settings")
def update_agent_settings(payload: AgentSettingsUpdate, request: Request, db: Session = Depends(get_db)):
    s = get_agent_settings(db, user_id=request.state.user_id)
    for key, value in payload.model_dump().items():
        setattr(s, key, value)
    db.commit()
    return {"message": "Configurações do agente salvas.", "settings": agent_settings_dict(db, request.state.user_id)}


class AgentRun(BaseModel):
    sources: Optional[list[str]] = None
    limit: int = Field(80, ge=1, le=80)
    collect: bool = True


@app.post("/api/agent/run")
def agent_run(payload: AgentRun, request: Request, db: Session = Depends(get_db)):
    names = payload.sources or list(SOURCES.keys())
    invalid = [n for n in names if n not in SOURCES]
    if invalid:
        raise HTTPException(400, f"Fontes sem coleta automática ou desconhecidas: {', '.join(invalid)}")
    return run_agent(db, sources=names, limit=payload.limit, collect=payload.collect, user_id=request.state.user_id)


@app.get("/api/sources")
def list_sources(request: Request, db: Session = Depends(get_db)):
    p = get_profile(db, request.state.user_id)
    terms = [t.strip() for t in (p.interests or "").split(",") if t.strip()][:3] or None
    return {"sources": [{"name": n, **info} for n, info in SOURCE_INFO.items()],
            "external_links": external_search_links(terms)}


@app.get("/api/applications")
def list_applications(request: Request, db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).options(joinedload(Application.job)).where(Application.user_id == request.state.user_id).order_by(Application.updated_at.desc())).unique().all()
    return [{
        "id": a.id, "job_id": a.job_id, "status": a.status,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "recruiter": a.recruiter or "", "notes": a.notes or "",
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "job": job_dict(a.job, with_application=False),
    } for a in apps]


@app.put("/api/applications/{application_id}")
def update_application(application_id: int, payload: ApplicationUpdate, request: Request, db: Session = Depends(get_db)):
    application = db.scalar(select(Application).where(Application.id == application_id, Application.user_id == request.state.user_id))
    if not application:
        raise HTTPException(404, "Candidatura não encontrada.")
    if payload.status not in STATUSES:
        raise HTTPException(400, "Etapa de candidatura inválida.")
    previous_status = application.status
    for key, value in payload.model_dump().items():
        setattr(application, key, value)
    if payload.status != previous_status:
        db.add(ApplicationEvent(
            user_id=request.state.user_id,
            application_id=application.id,
            previous_status=previous_status or "",
            new_status=payload.status,
            source="manual",
            note=(payload.notes or "").strip(),
        ))
    db.commit(); db.refresh(application)
    return {"message": "Candidatura atualizada."}




@app.get("/api/applications/{application_id}/history")
def application_history(application_id: int, request: Request, db: Session = Depends(get_db)):
    """Retorna somente os eventos vinculados à candidatura e conta autenticadas."""
    user_id = request.state.user_id
    application = db.scalar(select(Application).where(
        Application.id == application_id,
        Application.user_id == user_id,
    ))
    if application is None:
        raise HTTPException(404, "Candidatura não encontrada.")
    events = db.scalars(
        select(ApplicationEvent)
        .where(
            ApplicationEvent.application_id == application_id,
            ApplicationEvent.user_id == user_id,
        )
        .order_by(ApplicationEvent.occurred_at.asc(), ApplicationEvent.id.asc())
    ).all()
    return {
        "application_id": application.id,
        "has_history": bool(events),
        "events": [{
            "id": event.id,
            "previous_status": event.previous_status or "",
            "new_status": event.new_status,
            "source": event.source,
            "note": event.note or "",
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        } for event in events],
        "notice": (
            "O histórico é registrado a partir da ativação desta funcionalidade. "
            "Etapas anteriores não são inferidas retroativamente."
        ),
    }

@app.get("/api/tasks")
def list_tasks(request: Request, view: str = "Pendentes", db: Session = Depends(get_db)):
    stmt = select(Task).options(joinedload(Task.job)).where(Task.user_id == request.state.user_id).order_by(Task.due_date, Task.id.desc())
    if view == "Pendentes": stmt = stmt.where(Task.status != "Concluída")
    elif view == "Concluídas": stmt = stmt.where(Task.status == "Concluída")
    elif view == "Vencidas": stmt = stmt.where(Task.status != "Concluída", Task.due_date < date.today())
    return [task_dict(t) for t in db.scalars(stmt).unique().all()]


@app.post("/api/tasks")
def new_task(payload: TaskCreate, request: Request, db: Session = Depends(get_db)):
    if payload.job_id is not None:
        _require_user_job_match(db, payload.job_id, request.state.user_id)
    task = create_task(db, payload.title, payload.description, payload.due_date, payload.priority, payload.job_id, payload.notify, user_id=request.state.user_id)
    return {"message": "Tarefa criada.", "task": task_dict(task)}


@app.put("/api/tasks/{task_id}")
def edit_task(task_id: int, payload: TaskUpdate, request: Request, db: Session = Depends(get_db)):
    task = db.scalar(select(Task).options(joinedload(Task.job)).where(Task.id == task_id, Task.user_id == request.state.user_id))
    if not task: raise HTTPException(404, "Tarefa não encontrada.")
    task.title = payload.title; task.description = payload.description
    task.due_date = payload.due_date; task.priority = payload.priority
    task.status = payload.status; task.notify = payload.notify
    task.completed_at = datetime.utcnow() if payload.status == "Concluída" else None
    db.commit(); db.refresh(task)
    return {"message": "Tarefa atualizada.", "task": task_dict(task)}


@app.patch("/api/tasks/{task_id}/complete")
def finish_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == request.state.user_id))
    if not task: raise HTTPException(404, "Tarefa não encontrada.")
    complete_task(db, task)
    return {"message": "Tarefa concluída."}


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == request.state.user_id))
    if not task: raise HTTPException(404, "Tarefa não encontrada.")
    db.delete(task); db.commit()
    return {"message": "Tarefa excluída."}


@app.get("/api/profile")
def read_profile(request: Request, db: Session = Depends(get_db)):
    return profile_dict(get_profile(db, request.state.user_id))


@app.get("/api/career-twin")
def read_career_twin(request: Request, db: Session = Depends(get_db)):
    """Retorna a visão consolidada e explicável do perfil da conta autenticada."""
    return build_career_twin(db, user_id=request.state.user_id)


class CareerEvidenceReviewInput(BaseModel):
    decision: str = Field(pattern="^(confirmed|dismissed)$")
    note: str = Field("", max_length=1000)


@app.get("/api/career-evidence")
def read_career_evidence(
    request: Request,
    active_only: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Retorna o histórico de evidências exclusivamente da conta autenticada."""
    return {
        "items": list_profile_evidence(
            db, user_id=request.state.user_id, active_only=active_only, limit=limit
        )
    }


@app.post("/api/career-evidence/{evidence_id}/review")
def submit_career_evidence_review(
    evidence_id: int,
    payload: CareerEvidenceReviewInput,
    request: Request,
    db: Session = Depends(get_db),
):
    """Anexa decisão humana sem editar a evidência nem promover proficiência."""
    try:
        result = review_profile_evidence(
            db,
            evidence_id=evidence_id,
            user_id=request.state.user_id,
            decision=payload.decision,
            note=payload.note,
        )
        db.commit()
        return {"review": result}
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))


@app.get("/api/career-evidence/{evidence_id}/reviews")
def read_career_evidence_reviews(
    evidence_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Retorna decisões históricas sem permitir consultar evidência de outra conta."""
    try:
        return {
            "items": list_evidence_reviews(
                db, evidence_id=evidence_id, user_id=request.state.user_id
            )
        }
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@app.put("/api/profile")
def update_profile(payload: ProfileUpdate, request: Request, db: Session = Depends(get_db)):
    p = get_profile(db, request.state.user_id)
    data = payload.model_dump()
    collections = {
        "educations": (Education, ("course", "institution", "degree", "status", "start_date", "end_date", "description")),
        "experiences": (Experience, ("company", "role", "employment_type", "location", "start_date", "end_date", "is_current", "description")),
        "courses": (Course, ("name", "provider", "workload", "completed_at", "status", "credential_url")),
        "certifications_items": (Certification, ("name", "issuer", "issued_at", "expires_at", "credential_id", "credential_url")),
        "portfolio_projects": (PortfolioProject, ("name", "description", "technologies", "repository_url", "demo_url", "status")),
    }
    for key, (model, fields) in collections.items():
        records = data.pop(key)
        if records is not None:
            _sync_profile_records(getattr(p, key), records, model, fields)
    for key, value in data.items():
        if key.startswith("weight_"):
            value = max(0, min(100, value))
        setattr(p, key, value)
    # Garante IDs estáveis para novos registros estruturados antes de criar source_key.
    db.flush()
    ledger_sync = sync_profile_evidence(db, p, user_id=request.state.user_id)
    db.commit()
    refresh_user_scores(db, request.state.user_id)
    db.refresh(p)
    return {
        "message": "Perfil salvo, evidências atualizadas e compatibilidades recalculadas.",
        "profile": profile_dict(p),
        "evidence_sync": ledger_sync,
    }


MAX_RESUME_BYTES = 5 * 1024 * 1024
RESUME_IMPORTS_PER_HOUR = 5


@app.post("/api/profile/import")
async def import_resume(
    request: Request,
    file: UploadFile = File(...),
    allow_external_ai: bool = Form(False),
    store_for_applications: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Extrai sugestões sem salvar o arquivo nem enviar dados externos sem consentimento."""
    _enforce_rate_limit(
        db, request, scope="resume-import-user",
        subject=str(request.state.user_id), limit=RESUME_IMPORTS_PER_HOUR,
        window_seconds=3600,
    )
    filename = file.filename or ""
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(400, "Formato não suportado. Envie um arquivo PDF ou DOCX.")

    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    allowed_types = {
        ".pdf": {"application/pdf", "application/octet-stream"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        },
    }
    if content_type and content_type not in allowed_types[suffix]:
        raise HTTPException(415, "O tipo informado não corresponde a PDF ou DOCX.")

    content = await file.read(MAX_RESUME_BYTES + 1)
    await file.close()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(413, "O currículo deve ter no máximo 5 MB.")
    if not content:
        raise HTTPException(400, "O arquivo enviado está vazio.")
    if suffix == ".pdf" and b"%PDF-" not in content[:1024]:
        raise HTTPException(400, "O conteúdo não parece ser um PDF válido.")
    if suffix == ".docx" and not content.startswith(b"PK\x03\x04"):
        raise HTTPException(400, "O conteúdo não parece ser um DOCX válido.")

    try:
        resume_text = extract_resume_text(content, filename)
        if settings.gemini_api_key and allow_external_ai:
            extracted = analyze_resume_with_gemini(resume_text)
            analysis_mode = "gemini"
            message = "Currículo analisado com Gemini mediante sua autorização. Revise os campos e clique em Salvar perfil."
        else:
            extracted = parse_resume(content, filename)
            analysis_mode = "basic"
            if settings.gemini_api_key:
                message = "Currículo lido localmente. O Gemini está configurado, mas não foi acionado porque você não autorizou o envio do texto. Revise antes de salvar."
            else:
                message = "Currículo lido localmente pelo extrator básico. Revise as informações antes de salvar."
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except ResumeAIError as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        # Não registrar exceções que possam conter trechos do currículo ou dados pessoais.
        raise HTTPException(422, "Não foi possível ler este arquivo. Verifique se o PDF/DOCX está íntegro e tente novamente.")
    if not extracted:
        raise HTTPException(422, "Não encontramos informações reconhecíveis. Confira se o PDF permite selecionar/copiar o texto.")

    resume_storage_saved = False
    if store_for_applications:
        try:
            encrypted_content = encrypt_resume(content)
            stored_filename = safe_filename(filename)
            stored_type = resume_content_type(stored_filename)
        except ResumeStorageError as exc:
            raise HTTPException(503, str(exc)) from exc
        stored = db.scalar(select(UserResume).where(UserResume.user_id == request.state.user_id))
        if stored is None:
            stored = UserResume(
                user_id=request.state.user_id, filename=stored_filename,
                content_type=stored_type, encrypted_content=encrypted_content,
                sha256=hashlib.sha256(content).hexdigest(),
            )
            db.add(stored)
        else:
            stored.filename = stored_filename
            stored.content_type = stored_type
            stored.encrypted_content = encrypted_content
            stored.sha256 = hashlib.sha256(content).hexdigest()
        db.commit()
        resume_storage_saved = True
        message += " O arquivo original também foi armazenado cifrado para anexos de candidatura."

    return {
        "message": message, "analysis_mode": analysis_mode, "extracted": extracted,
        "resume_storage_saved": resume_storage_saved,
    }


@app.get("/api/profile/resume")
def read_stored_resume(request: Request, db: Session = Depends(get_db)):
    stored = db.scalar(select(UserResume).where(UserResume.user_id == request.state.user_id))
    return {
        "configured": stored is not None,
        "filename": stored.filename if stored else "",
        "updated_at": stored.updated_at.isoformat() if stored and stored.updated_at else None,
    }


@app.delete("/api/profile/resume")
def delete_stored_resume(request: Request, db: Session = Depends(get_db)):
    stored = db.scalar(select(UserResume).where(UserResume.user_id == request.state.user_id))
    if stored is not None:
        db.delete(stored)
        db.commit()
    return {"message": "Arquivo de currículo individual removido.", "configured": False}


@app.get("/api/notifications")
def notification_history(request: Request, db: Session = Depends(get_db)):
    logs = db.scalars(select(NotificationLog).where(NotificationLog.user_id == request.state.user_id).order_by(NotificationLog.created_at.desc()).limit(20)).all()
    return [{"id": x.id, "created_at": x.created_at.isoformat() if x.created_at else None,
             "status": x.status, "detail": x.detail} for x in logs]


@app.post("/api/notifications/send")
def send_notifications(request: Request):
    # O lembrete SMTP legado usa um destinatário global. Mantido bloqueado no SaaS
    # até existir configuração e envio isolados por usuário.
    raise HTTPException(503, "Envio de lembretes por e-mail ficará disponível quando a configuração individual estiver pronta.")



class MarketRunRequest(BaseModel):
    level_scope: str = Field("both", pattern="^(both|estagio|junior)$")
    days: int = Field(30, ge=1, le=365)


@app.post("/api/market/analysis/run")
def run_market_analysis(payload: MarketRunRequest, request: Request, db: Session = Depends(get_db)):
    """Indexa vagas alvo e cria um snapshot auditável de inteligência de mercado."""
    _enforce_rate_limit(
        db, request, scope="market-analysis-user",
        subject=str(request.state.user_id), limit=1, window_seconds=600,
    )
    try:
        indexed = index_unprocessed_jobs(db)
        result = create_market_snapshot(
            db, level_scope=payload.level_scope, days=payload.days
        )
        result["indexing"] = indexed
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/market/analysis/latest")
def latest_market_analysis(db: Session = Depends(get_db)):
    run = db.scalar(
        select(MarketAnalysisRun)
        .where(MarketAnalysisRun.status == "completed")
        .order_by(MarketAnalysisRun.created_at.desc(), MarketAnalysisRun.id.desc())
        .limit(1)
    )
    if run is None:
        return {"available": False, "message": "Ainda não existe uma análise de mercado."}

    rows = db.execute(
        select(MarketSkillMetric, Skill)
        .join(Skill, Skill.id == MarketSkillMetric.skill_id)
        .where(MarketSkillMetric.run_id == run.id)
        .order_by(MarketSkillMetric.rank)
    ).all()
    return {
        "available": True,
        "run": {
            "id": run.id, "created_at": run.created_at.isoformat() if run.created_at else None,
            "period_start": run.period_start.isoformat() if run.period_start else None,
            "period_end": run.period_end.isoformat() if run.period_end else None,
            "level_scope": run.level_scope, "total_jobs": run.total_jobs,
            "valid_jobs": run.valid_jobs, "jobs_with_description": run.jobs_with_description,
            "sources": __import__("json").loads(run.sources_json or "[]"),
            "taxonomy_version": run.taxonomy_version, "quality_notes": run.quality_notes,
        },
        "skills": [{
            "id": metric.id, "skill_id": skill.id, "name": skill.canonical_name,
            "category": skill.category, "jobs_count": metric.jobs_count,
            "mention_rate": round(metric.mention_rate * 100, 1), "rank": metric.rank,
        } for metric, skill in rows],
    }


@app.get("/api/market/profile-gap")
def market_profile_gap(request: Request, run_id: int | None = None, db: Session = Depends(get_db)):
    """Compara competências do snapshot com evidências registradas no perfil."""
    return build_profile_gap(db, user_id=request.state.user_id, run_id=run_id)




class DevelopmentItemCreate(BaseModel):
    skill_id: int = Field(gt=0)
    run_id: Optional[int] = Field(None, gt=0)
    title: str = Field("", max_length=220)
    objective: str = Field("", max_length=2000)
    activity: str = Field("", max_length=4000)
    resource_url: str = Field("", max_length=2000)
    estimated_hours: int = Field(4, ge=1, le=500)
    due_date: Optional[date] = None


class DevelopmentItemUpdate(BaseModel):
    status: Optional[str] = None
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    due_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=4000)
    title: Optional[str] = Field(None, min_length=1, max_length=220)
    objective: Optional[str] = Field(None, max_length=2000)
    activity: Optional[str] = Field(None, max_length=4000)
    estimated_hours: Optional[int] = Field(None, ge=1, le=500)
    resource_url: Optional[str] = Field(None, max_length=2000)


@app.get("/api/market/development-plan")
def get_market_development_plan(request: Request, db: Session = Depends(get_db)):
    return list_development_plan(db, user_id=request.state.user_id)


@app.post("/api/market/development-plan")
def add_market_development_item(payload: DevelopmentItemCreate, request: Request, db: Session = Depends(get_db)):
    try:
        item = create_development_item(db, **payload.model_dump(), user_id=request.state.user_id)
        return {"message": "Meta adicionada ao plano.", "item": item, "plan": list_development_plan(db, user_id=request.state.user_id)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/market/development-plan/{item_id}")
def edit_market_development_item(item_id: int, payload: DevelopmentItemUpdate, request: Request, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in DEVELOPMENT_STATUSES:
        raise HTTPException(400, "Status de desenvolvimento inválido.")
    try:
        item = update_development_item(db, item_id, data, user_id=request.state.user_id)
        return {"message": "Progresso atualizado.", "item": item}
    except ValueError as exc:
        raise HTTPException(404 if "não encontrada" in str(exc) else 400, str(exc))


@app.delete("/api/market/development-plan/{item_id}")
def delete_market_development_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.scalar(select(DevelopmentPlanItem).where(DevelopmentPlanItem.id == item_id, DevelopmentPlanItem.user_id == request.state.user_id))
    if item is None:
        raise HTTPException(404, "Meta de desenvolvimento não encontrada.")
    db.delete(item)
    db.commit()
    return {"message": "Meta removida do plano."}

class SkillAssessmentCreate(BaseModel):
    skill_id: int = Field(gt=0)
    plan_item_id: Optional[int] = Field(None, gt=0)


class SkillAssessmentSubmit(BaseModel):
    response_text: str = Field("", max_length=12000)
    evidence_url: str = Field("", max_length=2000)
    rubric_answers: dict[str, bool]


@app.get("/api/market/assessments")
def get_market_assessments(request: Request, skill_id: Optional[int] = Query(None, gt=0), db: Session = Depends(get_db)):
    return list_skill_assessments(db, user_id=request.state.user_id, skill_id=skill_id)


@app.post("/api/market/assessments")
def start_market_assessment(payload: SkillAssessmentCreate, request: Request, db: Session = Depends(get_db)):
    try:
        return {"attempt": create_skill_assessment(db, **payload.model_dump(), user_id=request.state.user_id)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/market/assessments/{attempt_id}/submit")
def submit_market_assessment(attempt_id: int, payload: SkillAssessmentSubmit, request: Request, db: Session = Depends(get_db)):
    try:
        attempt = submit_skill_assessment(db, attempt_id, **payload.model_dump(), user_id=request.state.user_id)
        evidence = record_self_assessment_evidence(
            db, attempt_id=attempt_id, user_id=request.state.user_id
        )
        db.commit()
        return {"message": "Autoavaliação registrada.", "attempt": attempt, "evidence": evidence}
    except ValueError as exc:
        raise HTTPException(404 if "não encontrado" in str(exc) else 400, str(exc))





@app.get("/api/market/trends")
def market_skill_trends(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Compara snapshots equivalentes sem misturar janelas ou versões."""
    return compare_market_trends(db, limit=limit)


@app.get("/api/market/analysis/history")
def market_analysis_history(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    runs = db.scalars(
        select(MarketAnalysisRun)
        .where(MarketAnalysisRun.status == "completed")
        .order_by(MarketAnalysisRun.created_at.desc(), MarketAnalysisRun.id.desc())
        .limit(limit)
    ).all()
    return [{
        "id": run.id, "created_at": run.created_at.isoformat() if run.created_at else None,
        "period_start": run.period_start.isoformat() if run.period_start else None,
        "period_end": run.period_end.isoformat() if run.period_end else None,
        "level_scope": run.level_scope, "total_jobs": run.total_jobs,
        "valid_jobs": run.valid_jobs, "quality_notes": run.quality_notes,
    } for run in runs]



@app.get("/api/market/combinations")
def market_skill_combinations(
    run_id: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retorna combinações de competências observadas no snapshot mais recente ou indicado."""
    selected_run = db.get(MarketAnalysisRun, run_id) if run_id else db.scalar(
        select(MarketAnalysisRun)
        .where(MarketAnalysisRun.status == "completed")
        .order_by(MarketAnalysisRun.created_at.desc(), MarketAnalysisRun.id.desc())
        .limit(1)
    )
    if selected_run is None or selected_run.status != "completed":
        return {"available": False, "combinations": []}

    skill_a = aliased(Skill)
    skill_b = aliased(Skill)
    rows = db.execute(
        select(MarketSkillPair, skill_a, skill_b)
        .join(skill_a, skill_a.id == MarketSkillPair.skill_a_id)
        .join(skill_b, skill_b.id == MarketSkillPair.skill_b_id)
        .where(MarketSkillPair.run_id == selected_run.id)
        .order_by(MarketSkillPair.jobs_count.desc())
        .limit(limit)
    ).all()
    return {
        "available": True,
        "run_id": selected_run.id,
        "total_jobs": selected_run.total_jobs,
        "combinations": [{
            "skill_a": first.canonical_name,
            "skill_b": second.canonical_name,
            "jobs_count": pair.jobs_count,
            "mention_rate": round(pair.pair_rate * 100, 1),
        } for pair, first, second in rows],
    }
