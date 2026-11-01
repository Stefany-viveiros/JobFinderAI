from datetime import date, datetime
from email.message import EmailMessage
import hashlib
import secrets
import smtplib
from datetime import timedelta
from pwdlib import PasswordHash
from .models import User, UserSession, PasswordResetToken
from .auth import SESSION_COOKIE, COOKIE_SECURE, create_session, clear_session_cookie
import os
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload, aliased

from .db import init_db, SessionLocal
from .models import (
    Job, JobMatch, Application, Task, Profile, NotificationLog, ApplicationAttempt,
    Education, Experience, Course, Certification, PortfolioProject,
    MarketAnalysisRun, MarketSkillMetric, MarketSkillPair, Skill, DevelopmentPlanItem,
)
from .service import get_profile, save_jobs, refresh_scores, create_task, complete_task, STATUSES, collect_and_save_ranked
from .sources import SOURCES, SOURCE_INFO, LINK_ONLY_SOURCES, collect_selected, external_search_links
from . import applying
from .agent import get_agent_settings, run_agent, TARGET_LEVELS
from .mailer import send_daily_reminder
from .config import settings
from .resume_parser import parse_resume, extract_resume_text
from .resume_ai import analyze_resume_with_gemini, ResumeAIError
from .market_service import (create_market_snapshot, index_unprocessed_jobs, build_profile_gap,
    list_development_plan, create_development_item, update_development_item, DEVELOPMENT_STATUSES,
    create_skill_assessment, submit_skill_assessment, list_skill_assessments)

app = FastAPI(title="JobFinder AI API", version="1.1.0", description="API do JobFinder AI")
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
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
        "/api/auth/logout", "/api/auth/forgot-password", "/api/auth/reset-password",
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


def _public_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@app.post("/api/auth/register")
def register(payload: RegisterInput, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip()
    normalized = email.casefold()
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
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email_normalized == payload.email.strip().casefold()))
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
def forgot_password(payload: ForgotPasswordInput, db: Session = Depends(get_db)):
    # Resposta idêntica exista ou não a conta, para não revelar cadastros.
    user = db.scalar(select(User).where(User.email_normalized == payload.email.strip().casefold()))
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
def reset_password(payload: ResetPasswordInput, db: Session = Depends(get_db)):
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
    user.password_hash = password_hasher.hash(payload.password)
    reset.used_at = datetime.utcnow()
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
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    url = payload.url.strip()
    if not url:
        raise HTTPException(400, "Informe o link original da vaga.")
    item = payload.model_dump()
    item.update({"source": "Manual", "source_id": None, "published_at": payload.published_at})
    count = save_jobs([item])
    existing = db.scalar(select(Job).where(Job.url == url))
    if not existing:
        raise HTTPException(400, "Não foi possível salvar a vaga.")
    if count == 0:
        return {"message": "Link já cadastrado.", "job": job_dict(existing)}
    db.refresh(existing)
    return {"message": "Vaga salva com sucesso.", "job": job_dict(existing)}


@app.post("/api/jobs/collect")
def collect_jobs(payload: dict, db: Session = Depends(get_db)):
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
    result = collect_and_save_ranked(items, limit, only_target=bool(payload.get("only_target", True)))

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


@app.patch("/api/jobs/{job_id}/favorite")
def toggle_favorite(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    user_id = request.state.user_id
    match = db.scalar(select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.user_id == user_id))
    if match is None:
        match = JobMatch(job_id=job.id, user_id=user_id)
        db.add(match)
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
    try:
        attempt = applying.prepare_attempt(db, job, get_profile(db, request.state.user_id), user_id=request.state.user_id)
    except applying.ApplyError as exc:
        raise HTTPException(400, str(exc))
    msg = ("Candidatura preparada. Revise e aprove o envio." if attempt.channel == "email"
           else "Candidatura preparada. Abra a vaga, finalize no site e confirme o envio manualmente.")
    return {"message": msg, "attempt": attempt_dict(attempt, with_message=True)}


@app.get("/api/attempts")
def list_attempts(request: Request, status: str = "todas", limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db)):
    stmt = select(ApplicationAttempt).options(joinedload(ApplicationAttempt.job)).where(ApplicationAttempt.user_id == request.state.user_id).order_by(ApplicationAttempt.id.desc()).limit(limit)
    if status != "todas":
        stmt = stmt.where(ApplicationAttempt.status == status)
    return [{**attempt_dict(a, with_message=True), "job": {
        "id": a.job.id, "title": a.job.title, "company": a.job.company, "url": a.job.url,
        "compatibility": round(a.job.compatibility or 0), "source": a.job.source,
        "missing_reasons": a.job.missing_reasons or ""}}
        for a in db.scalars(stmt).unique().all()]


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
    if attempt.job and (attempt.job.compatibility or 0) < agent_settings.min_score:
        raise HTTPException(
            409,
            f"Compatibilidade atual ({round(attempt.job.compatibility or 0)}%) abaixo do mínimo configurado "
            f"({agent_settings.min_score}%). Revise a vaga antes de aprovar."
        )
    if attempt.job and "Requisito(s) obrigatório(s) não identificado(s)" in (attempt.job.missing_reasons or ""):
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
    attempt = _attempt_or_404(db, attempt_id)
    try:
        applying.cancel_attempt(db, attempt)
    except applying.ApplyError as exc:
        raise HTTPException(409, str(exc))
    return {"message": "Candidatura cancelada.", "attempt": attempt_dict(attempt)}


class AgentSettingsUpdate(BaseModel):
    auto_apply_enabled: bool = False
    require_approval: bool = True
    daily_limit: int = Field(5, ge=0, le=50)
    min_score: int = Field(80, ge=0, le=100)


def agent_settings_dict(db, user_id=None):
    s = get_agent_settings(db, user_id=user_id)
    p = get_profile(db, user_id=user_id)
    return {"auto_apply_enabled": s.auto_apply_enabled, "require_approval": s.require_approval,
            "daily_limit": s.daily_limit, "min_score": s.min_score,
            "sent_today": applying.sent_today_count(db),
            "email_ready": settings.smtp_can_send_applications,
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
    for key, value in payload.model_dump().items():
        setattr(application, key, value)
    db.commit(); db.refresh(application)
    return {"message": "Candidatura atualizada."}


@app.get("/api/tasks")
def list_tasks(request: Request, view: str = "Pendentes", db: Session = Depends(get_db)):
    stmt = select(Task).options(joinedload(Task.job)).where(Task.user_id == request.state.user_id).order_by(Task.due_date, Task.id.desc())
    if view == "Pendentes": stmt = stmt.where(Task.status != "Concluída")
    elif view == "Concluídas": stmt = stmt.where(Task.status == "Concluída")
    elif view == "Vencidas": stmt = stmt.where(Task.status != "Concluída", Task.due_date < date.today())
    return [task_dict(t) for t in db.scalars(stmt).unique().all()]


@app.post("/api/tasks")
def new_task(payload: TaskCreate, request: Request, db: Session = Depends(get_db)):
    if payload.job_id is not None and not db.get(Job, payload.job_id):
        raise HTTPException(404, "Vaga associada não encontrada.")
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
    db.commit()
    refresh_scores(db)
    db.refresh(p)
    return {"message": "Perfil salvo e compatibilidades recalculadas.", "profile": profile_dict(p)}


@app.post("/api/profile/import")
async def import_resume(file: UploadFile = File(...)):
    """Extrai sugestões do currículo sem salvar nem sobrescrever o perfil."""
    filename = file.filename or ""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in {"pdf", "docx"}:
        raise HTTPException(400, "Formato não suportado. Envie um arquivo PDF ou DOCX.")
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "O currículo deve ter no máximo 5 MB.")
    if not content:
        raise HTTPException(400, "O arquivo enviado está vazio.")
    try:
        # A IA recebe o texto extraído integralmente; o arquivo original não é salvo.
        resume_text = extract_resume_text(content, filename)
        if settings.gemini_api_key:
            extracted = analyze_resume_with_gemini(resume_text)
            analysis_mode = "gemini"
            message = "Currículo analisado com Gemini. Revise os campos preenchidos e clique em Salvar perfil."
        else:
            # Mantém compatibilidade para instalações ainda sem a variável de ambiente.
            extracted = parse_resume(content, filename)
            analysis_mode = "basic"
            message = "Currículo lido pelo extrator básico. Configure GEMINI_API_KEY no servidor para ativar a análise inteligente. Revise antes de salvar."
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except ResumeAIError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(422, "Não foi possível ler este arquivo. Verifique se o PDF/DOCX está íntegro e tente novamente.")
    if not extracted:
        raise HTTPException(422, "Não encontramos informações reconhecíveis. Confira se o PDF permite selecionar/copiar o texto.")
    return {"message": message, "analysis_mode": analysis_mode, "extracted": extracted}


@app.get("/api/notifications")
def notification_history(request: Request, db: Session = Depends(get_db)):
    logs = db.scalars(select(NotificationLog).where(NotificationLog.user_id == request.state.user_id).order_by(NotificationLog.created_at.desc()).limit(20)).all()
    return [{"id": x.id, "created_at": x.created_at.isoformat() if x.created_at else None,
             "status": x.status, "detail": x.detail} for x in logs]


@app.post("/api/notifications/send")
def send_notifications():
    # O lembrete SMTP legado usa um destinatário global. Mantido bloqueado no SaaS
    # até existir configuração e envio isolados por usuário.
    raise HTTPException(503, "Envio de lembretes por e-mail ficará disponível quando a configuração individual estiver pronta.")



class MarketRunRequest(BaseModel):
    level_scope: str = Field("both", pattern="^(both|estagio|junior)$")
    days: int = Field(30, ge=1, le=365)


@app.post("/api/market/analysis/run")
def run_market_analysis(payload: MarketRunRequest, db: Session = Depends(get_db)):
    """Indexa vagas alvo e cria um snapshot auditável de inteligência de mercado."""
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
def market_profile_gap(run_id: int | None = None, db: Session = Depends(get_db)):
    """Compara competências do snapshot com evidências registradas no perfil."""
    return build_profile_gap(db, run_id=run_id)




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
def get_market_development_plan(db: Session = Depends(get_db)):
    return list_development_plan(db)


@app.post("/api/market/development-plan")
def add_market_development_item(payload: DevelopmentItemCreate, db: Session = Depends(get_db)):
    try:
        item = create_development_item(db, **payload.model_dump())
        return {"message": "Meta adicionada ao plano.", "item": item, "plan": list_development_plan(db)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/market/development-plan/{item_id}")
def edit_market_development_item(item_id: int, payload: DevelopmentItemUpdate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in DEVELOPMENT_STATUSES:
        raise HTTPException(400, "Status de desenvolvimento inválido.")
    try:
        item = update_development_item(db, item_id, data)
        return {"message": "Progresso atualizado.", "item": item}
    except ValueError as exc:
        raise HTTPException(404 if "não encontrada" in str(exc) else 400, str(exc))


@app.delete("/api/market/development-plan/{item_id}")
def delete_market_development_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(DevelopmentPlanItem, item_id)
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
def get_market_assessments(skill_id: Optional[int] = Query(None, gt=0), db: Session = Depends(get_db)):
    return list_skill_assessments(db, skill_id=skill_id)


@app.post("/api/market/assessments")
def start_market_assessment(payload: SkillAssessmentCreate, db: Session = Depends(get_db)):
    try:
        return {"attempt": create_skill_assessment(db, **payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/market/assessments/{attempt_id}/submit")
def submit_market_assessment(attempt_id: int, payload: SkillAssessmentSubmit, db: Session = Depends(get_db)):
    try:
        attempt = submit_skill_assessment(db, attempt_id, **payload.model_dump())
        return {"message": "Autoavaliação registrada.", "attempt": attempt}
    except ValueError as exc:
        raise HTTPException(404 if "não encontrado" in str(exc) else 400, str(exc))



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
