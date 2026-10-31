from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from .db import init_db, SessionLocal
from .models import (
    Job, Application, Task, Profile, NotificationLog, ApplicationAttempt,
    Education, Experience, Course, Certification, PortfolioProject,
)
from .service import get_profile, save_jobs, refresh_scores, create_task, complete_task, STATUSES, collect_and_save_ranked
from .sources import SOURCES, SOURCE_INFO, LINK_ONLY_SOURCES, collect_selected, external_search_links
from . import applying
from .agent import get_agent_settings, run_agent, TARGET_LEVELS
from .mailer import send_daily_reminder
from .config import settings
from .resume_parser import parse_resume, extract_resume_text
from .resume_ai import analyze_resume_with_gemini, ResumeAIError

app = FastAPI(title="JobFinder AI API", version="1.1.0", description="API local do JobFinder AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup():
    init_db()
    # Cria o perfil singleton antes de aceitar chamadas paralelas do frontend.
    db = SessionLocal()
    try:
        get_profile(db)
    finally:
        db.close()


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


def job_dict(j: Job, with_application=True):
    application = None
    if with_application and j.application:
        application = {
            "id": j.application.id, "status": j.application.status,
            "applied_at": j.application.applied_at.isoformat() if j.application.applied_at else None,
            "deadline": j.application.deadline.isoformat() if j.application.deadline else None,
            "recruiter": j.application.recruiter or "", "notes": j.application.notes or "",
        }
    return {
        "id": j.id, "source": j.source, "source_id": j.source_id,
        "title": j.title, "company": j.company, "description": j.description or "",
        "location": j.location, "modality": j.modality, "job_type": j.job_type,
        "published_at": j.published_at or "", "url": j.url,
        "compatibility": round(j.compatibility or 0),
        "match_reasons": j.match_reasons or "", "missing_reasons": j.missing_reasons or "",
        "is_favorite": bool(j.is_favorite), "is_archived": bool(j.is_archived),
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "level": j.level or "",
        "application": application,
        "latest_attempt": attempt_dict(j.attempts[-1]) if j.attempts else None,
    }


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
        data = payload.model_dump(exclude={"id"})
        data = {key: (value.strip() if isinstance(value, str) else value) for key, value in data.items()}
        if not any(value for value in data.values()):
            continue
        item_id = payload.id
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


def count_attempts_channel(db, channel):
    return db.scalar(select(func.count(func.distinct(ApplicationAttempt.job_id))).where(
        ApplicationAttempt.status == "sent", ApplicationAttempt.channel == channel)) or 0


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Job.id)).where(Job.is_archived.is_(False))) or 0
    new = db.scalar(select(func.count(Job.id)).where(Job.is_archived.is_(False), ~Job.application.has())) or 0
    saved = db.scalar(select(func.count(Job.id)).where(Job.is_favorite.is_(True), Job.is_archived.is_(False))) or 0
    apps = db.scalar(select(func.count(Application.id))) or 0
    interviews = db.scalar(select(func.count(Application.id)).where(Application.status == "Entrevista")) or 0
    pending = db.scalar(select(func.count(Task.id)).where(Task.status != "Concluída")) or 0
    overdue = db.scalar(select(func.count(Task.id)).where(Task.status != "Concluída", Task.due_date < date.today())) or 0
    avg_score = db.scalar(select(func.avg(Job.compatibility)).where(Job.is_archived.is_(False))) or 0
    upcoming = db.scalars(select(Task).options(joinedload(Task.job)).where(
        Task.status != "Concluída", Task.due_date.is_not(None)
    ).order_by(Task.due_date).limit(6)).all()
    recent_jobs = db.scalars(select(Job).options(joinedload(Job.application), selectinload(Job.attempts)).where(
        Job.is_archived.is_(False)
    ).order_by(Job.created_at.desc()).limit(5)).unique().all()
    p = get_profile(db)
    agent = get_agent_settings(db)
    count_attempts = lambda *statuses: db.scalar(select(func.count(func.distinct(ApplicationAttempt.job_id))).where(
        ApplicationAttempt.status.in_(statuses))) or 0
    compatible = db.scalar(select(func.count(Job.id)).where(
        Job.is_archived.is_(False), Job.level.in_(TARGET_LEVELS), Job.compatibility >= agent.min_score)) or 0
    target_jobs = db.scalar(select(func.count(Job.id)).where(
        Job.is_archived.is_(False), Job.level.in_(TARGET_LEVELS))) or 0
    return {
        "metrics": {"total_jobs": total, "new_jobs": new, "favorites": saved,
                    "applications": apps, "interviews": interviews, "pending_tasks": pending,
                    "overdue_tasks": overdue, "average_compatibility": round(avg_score),
                    "target_jobs": target_jobs, "compatible_jobs": compatible,
                    "min_score": agent.min_score,
                    "sent_applications": count_attempts("sent"),
                    "sent_automatically": count_attempts_channel(db, "email"),
                    "sent_manually_confirmed": count_attempts_channel(db, "manual_confirmed"),
                    "pending_applications": count_attempts("prepared", "awaiting_approval", "manual_required"),
                    "awaiting_approval": count_attempts("awaiting_approval"),
                    "failed_applications": count_attempts("failed")},
        "upcoming_tasks": [task_dict(t) for t in upcoming],
        "recent_jobs": [job_dict(j) for j in recent_jobs],
        "profile_name": p.name,
        "smtp_ready": bool(settings.smtp_ready and settings.smtp_username and settings.smtp_password),
    }


@app.get("/api/jobs")
def list_jobs(
    q: str = "", min_score: int = Query(0, ge=0, le=100), favorite: bool = False,
    modality: str = "Todas", sort: str = "Compatibilidade", only_new: bool = False,
    level: str = "todas", source: str = "Todas", attempt_status: str = "todas",
    limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)
):
    stmt = select(Job).options(joinedload(Job.application), selectinload(Job.attempts)).where(
        Job.is_archived.is_(False), Job.compatibility >= min_score)
    if level == "alvo":
        stmt = stmt.where(Job.level.in_(TARGET_LEVELS))
    elif level in ("estagio", "junior", "outro"):
        stmt = stmt.where(Job.level == level)
    if source != "Todas":
        stmt = stmt.where(Job.source == source)
    if attempt_status == "sem_tentativa":
        stmt = stmt.where(~Job.attempts.any())
    elif attempt_status != "todas":
        stmt = stmt.where(Job.attempts.any(ApplicationAttempt.status == attempt_status))
    if favorite:
        stmt = stmt.where(Job.is_favorite.is_(True))
    if modality != "Todas":
        stmt = stmt.where(Job.modality.ilike(f"%{modality}%"))
    if q.strip():
        search = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(search), Job.company.ilike(search), Job.description.ilike(search)))
    if only_new:
        stmt = stmt.where(~Job.application.has())
    stmt = stmt.order_by(Job.compatibility.desc() if sort == "Compatibilidade" else Job.created_at.desc()).limit(limit)
    return [job_dict(j) for j in db.scalars(stmt).unique().all()]


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
def toggle_favorite(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    job.is_favorite = not job.is_favorite
    db.commit()
    return {"id": job.id, "is_favorite": job.is_favorite}


class ConfirmSent(BaseModel):
    confirmed: bool = False
    note: str = ""


@app.post("/api/jobs/{job_id}/apply")
def apply_to_job(job_id: int, payload: ConfirmSent, db: Session = Depends(get_db)):
    """Registra candidatura feita MANUALMENTE pelo usuário. Exige confirmed=true: abrir a vaga ou
    preparar o texto não conta como envio."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    if not payload.confirmed:
        raise HTTPException(400, "Confirme que você já enviou a candidatura no site da vaga.")
    try:
        attempt = applying.confirm_manual_send(db, job, payload.note)
    except applying.ApplyError as exc:
        raise HTTPException(409, str(exc))
    app_row = db.scalar(select(Application).where(Application.job_id == job.id))
    return {"message": "Candidatura registrada como enviada (confirmação manual).",
            "application_id": app_row.id if app_row else None, "attempt": attempt_dict(attempt)}


@app.post("/api/jobs/{job_id}/prepare")
def prepare_job_application(job_id: int, db: Session = Depends(get_db)):
    """Prepara o texto e define o canal. Não envia e não marca como enviada."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    try:
        attempt = applying.prepare_attempt(db, job, get_profile(db))
    except applying.ApplyError as exc:
        raise HTTPException(400, str(exc))
    msg = ("Candidatura preparada. Revise e aprove o envio." if attempt.channel == "email"
           else "Candidatura preparada. Abra a vaga, finalize no site e confirme o envio manualmente.")
    return {"message": msg, "attempt": attempt_dict(attempt, with_message=True)}


@app.get("/api/attempts")
def list_attempts(status: str = "todas", limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db)):
    stmt = select(ApplicationAttempt).options(joinedload(ApplicationAttempt.job)).order_by(ApplicationAttempt.id.desc()).limit(limit)
    if status != "todas":
        stmt = stmt.where(ApplicationAttempt.status == status)
    return [{**attempt_dict(a, with_message=True), "job": {
        "id": a.job.id, "title": a.job.title, "company": a.job.company, "url": a.job.url,
        "compatibility": round(a.job.compatibility or 0), "source": a.job.source}}
        for a in db.scalars(stmt).unique().all()]


def _attempt_or_404(db, attempt_id):
    attempt = db.get(ApplicationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Tentativa de candidatura não encontrada.")
    return attempt


@app.post("/api/attempts/{attempt_id}/approve")
def approve_attempt(attempt_id: int, db: Session = Depends(get_db)):
    """Aprova e envia por e-mail. O status final reflete o resultado real do envio."""
    attempt = _attempt_or_404(db, attempt_id)
    limit = get_agent_settings(db).daily_limit
    try:
        applying.send_attempt(db, attempt, limit)
    except applying.ApplyError as exc:
        raise HTTPException(400, str(exc))
    message = "Candidatura enviada." if attempt.status == "sent" else f"O envio falhou: {attempt.detail}"
    return {"message": message, "attempt": attempt_dict(attempt)}


@app.post("/api/attempts/{attempt_id}/cancel")
def cancel_attempt(attempt_id: int, db: Session = Depends(get_db)):
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
    min_score: int = Field(60, ge=0, le=100)


def agent_settings_dict(db):
    s = get_agent_settings(db)
    p = get_profile(db)
    return {"auto_apply_enabled": s.auto_apply_enabled, "require_approval": s.require_approval,
            "daily_limit": s.daily_limit, "min_score": s.min_score,
            "sent_today": applying.sent_today_count(db),
            "email_ready": settings.smtp_can_send_applications,
            "profile_gaps": applying.profile_gaps(p), "profile_ready": not applying.profile_gaps(p)}


@app.get("/api/agent/settings")
def read_agent_settings(db: Session = Depends(get_db)):
    return agent_settings_dict(db)


@app.put("/api/agent/settings")
def update_agent_settings(payload: AgentSettingsUpdate, db: Session = Depends(get_db)):
    s = get_agent_settings(db)
    for key, value in payload.model_dump().items():
        setattr(s, key, value)
    db.commit()
    return {"message": "Configurações do agente salvas.", "settings": agent_settings_dict(db)}


class AgentRun(BaseModel):
    sources: Optional[list[str]] = None
    limit: int = Field(80, ge=1, le=80)
    collect: bool = True


@app.post("/api/agent/run")
def agent_run(payload: AgentRun, db: Session = Depends(get_db)):
    names = payload.sources or list(SOURCES.keys())
    invalid = [n for n in names if n not in SOURCES]
    if invalid:
        raise HTTPException(400, f"Fontes sem coleta automática ou desconhecidas: {', '.join(invalid)}")
    return run_agent(db, sources=names, limit=payload.limit, collect=payload.collect)


@app.get("/api/sources")
def list_sources(db: Session = Depends(get_db)):
    p = get_profile(db)
    terms = [t.strip() for t in (p.interests or "").split(",") if t.strip()][:3] or None
    return {"sources": [{"name": n, **info} for n, info in SOURCE_INFO.items()],
            "external_links": external_search_links(terms)}


@app.get("/api/applications")
def list_applications(db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).options(joinedload(Application.job)).order_by(Application.updated_at.desc())).unique().all()
    return [{
        "id": a.id, "job_id": a.job_id, "status": a.status,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "recruiter": a.recruiter or "", "notes": a.notes or "",
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "job": job_dict(a.job, with_application=False),
    } for a in apps]


@app.put("/api/applications/{application_id}")
def update_application(application_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)):
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(404, "Candidatura não encontrada.")
    if payload.status not in STATUSES:
        raise HTTPException(400, "Etapa de candidatura inválida.")
    for key, value in payload.model_dump().items():
        setattr(application, key, value)
    db.commit(); db.refresh(application)
    return {"message": "Candidatura atualizada."}


@app.get("/api/tasks")
def list_tasks(view: str = "Pendentes", db: Session = Depends(get_db)):
    stmt = select(Task).options(joinedload(Task.job)).order_by(Task.due_date, Task.id.desc())
    if view == "Pendentes": stmt = stmt.where(Task.status != "Concluída")
    elif view == "Concluídas": stmt = stmt.where(Task.status == "Concluída")
    elif view == "Vencidas": stmt = stmt.where(Task.status != "Concluída", Task.due_date < date.today())
    return [task_dict(t) for t in db.scalars(stmt).unique().all()]


@app.post("/api/tasks")
def new_task(payload: TaskCreate, db: Session = Depends(get_db)):
    if payload.job_id is not None and not db.get(Job, payload.job_id):
        raise HTTPException(404, "Vaga associada não encontrada.")
    task = create_task(db, payload.title, payload.description, payload.due_date, payload.priority, payload.job_id, payload.notify)
    return {"message": "Tarefa criada.", "task": task_dict(task)}


@app.put("/api/tasks/{task_id}")
def edit_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.scalar(select(Task).options(joinedload(Task.job)).where(Task.id == task_id))
    if not task: raise HTTPException(404, "Tarefa não encontrada.")
    task.title = payload.title; task.description = payload.description
    task.due_date = payload.due_date; task.priority = payload.priority
    task.status = payload.status; task.notify = payload.notify
    task.completed_at = datetime.utcnow() if payload.status == "Concluída" else None
    db.commit(); db.refresh(task)
    return {"message": "Tarefa atualizada.", "task": task_dict(task)}


@app.patch("/api/tasks/{task_id}/complete")
def finish_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task: raise HTTPException(404, "Tarefa não encontrada.")
    complete_task(db, task)
    return {"message": "Tarefa concluída."}


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task: raise HTTPException(404, "Tarefa não encontrada.")
    db.delete(task); db.commit()
    return {"message": "Tarefa excluída."}


@app.get("/api/profile")
def read_profile(db: Session = Depends(get_db)):
    return profile_dict(get_profile(db))


@app.put("/api/profile")
def update_profile(payload: ProfileUpdate, db: Session = Depends(get_db)):
    p = get_profile(db)
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
def notification_history(db: Session = Depends(get_db)):
    logs = db.scalars(select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(20)).all()
    return [{"id": x.id, "created_at": x.created_at.isoformat() if x.created_at else None,
             "status": x.status, "detail": x.detail} for x in logs]


@app.post("/api/notifications/send")
def send_notifications(db: Session = Depends(get_db)):
    if not (settings.smtp_ready and settings.smtp_username and settings.smtp_password):
        raise HTTPException(400, "Configure as variáveis SMTP no arquivo .env antes de enviar lembretes.")
    result = send_daily_reminder(db)
    return {"result": result}
