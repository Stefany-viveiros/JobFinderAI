from datetime import datetime, date
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(80), default="manual")
    source_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200), default="Empresa não informada")
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(200), default="Não informada")
    modality: Mapped[str] = mapped_column(String(50), default="Não informada")
    job_type: Mapped[str] = mapped_column(String(80), default="Não informado")
    published_at: Mapped[str] = mapped_column(String(80), default="")
    url: Mapped[str] = mapped_column(Text, unique=True)
    compatibility: Mapped[float] = mapped_column(Float, default=0)
    match_reasons: Mapped[str] = mapped_column(Text, default="")
    missing_reasons: Mapped[str] = mapped_column(Text, default="")
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dedupe_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    level: Mapped[str] = mapped_column(String(20), default="")  # estagio | junior | outro
    attempts: Mapped[list["ApplicationAttempt"]] = relationship(back_populates="job", cascade="all, delete-orphan", order_by="ApplicationAttempt.id")
    application: Mapped["Application | None"] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="job", cascade="all, delete-orphan")

class Profile(Base):
    __tablename__ = "profile"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(150), default="")
    course: Mapped[str] = mapped_column(String(200), default="")
    institution: Mapped[str] = mapped_column(String(200), default="")
    academic_stage: Mapped[str] = mapped_column(String(100), default="")
    technologies: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[str] = mapped_column(Text, default="")
    experience: Mapped[str] = mapped_column(Text, default="")
    projects: Mapped[str] = mapped_column(Text, default="")
    certifications: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")
    interests: Mapped[str] = mapped_column(Text, default="Estágio em Tecnologia")
    location: Mapped[str] = mapped_column(String(200), default="")
    modality: Mapped[str] = mapped_column(String(100), default="Remoto, Híbrido, Presencial")
    job_types: Mapped[str] = mapped_column(String(200), default="Estágio, Júnior")
    exclude_terms: Mapped[str] = mapped_column(Text, default="")
    weight_keywords: Mapped[int] = mapped_column(Integer, default=40)
    weight_area: Mapped[int] = mapped_column(Integer, default=25)
    weight_modality: Mapped[int] = mapped_column(Integer, default=15)
    weight_location: Mapped[int] = mapped_column(Integer, default=10)
    weight_level: Mapped[int] = mapped_column(Integer, default=10)

    educations: Mapped[list["Education"]] = relationship(back_populates="profile", cascade="all, delete-orphan", order_by="Education.id")
    experiences: Mapped[list["Experience"]] = relationship(back_populates="profile", cascade="all, delete-orphan", order_by="Experience.id")
    courses: Mapped[list["Course"]] = relationship(back_populates="profile", cascade="all, delete-orphan", order_by="Course.id")
    certifications_items: Mapped[list["Certification"]] = relationship(back_populates="profile", cascade="all, delete-orphan", order_by="Certification.id")
    portfolio_projects: Mapped[list["PortfolioProject"]] = relationship(back_populates="profile", cascade="all, delete-orphan", order_by="PortfolioProject.id")


class Education(Base):
    __tablename__ = "profile_educations"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    course: Mapped[str] = mapped_column(String(200), default="")
    institution: Mapped[str] = mapped_column(String(200), default="")
    degree: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="Em andamento")
    start_date: Mapped[str] = mapped_column(String(30), default="")
    end_date: Mapped[str] = mapped_column(String(30), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[Profile] = relationship(back_populates="educations")


class Experience(Base):
    __tablename__ = "profile_experiences"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(160), default="")
    employment_type: Mapped[str] = mapped_column(String(60), default="")
    location: Mapped[str] = mapped_column(String(160), default="")
    start_date: Mapped[str] = mapped_column(String(30), default="")
    end_date: Mapped[str] = mapped_column(String(30), default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[Profile] = relationship(back_populates="experiences")


class Course(Base):
    __tablename__ = "profile_courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(220), default="")
    provider: Mapped[str] = mapped_column(String(180), default="")
    workload: Mapped[str] = mapped_column(String(40), default="")
    completed_at: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(40), default="Concluído")
    credential_url: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[Profile] = relationship(back_populates="courses")


class Certification(Base):
    __tablename__ = "profile_certifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(220), default="")
    issuer: Mapped[str] = mapped_column(String(180), default="")
    issued_at: Mapped[str] = mapped_column(String(30), default="")
    expires_at: Mapped[str] = mapped_column(String(30), default="")
    credential_id: Mapped[str] = mapped_column(String(160), default="")
    credential_url: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[Profile] = relationship(back_populates="certifications_items")


class PortfolioProject(Base):
    __tablename__ = "profile_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(220), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    technologies: Mapped[str] = mapped_column(Text, default="")
    repository_url: Mapped[str] = mapped_column(Text, default="")
    demo_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="Em desenvolvimento")
    profile: Mapped[Profile] = relationship(back_populates="portfolio_projects")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    status: Mapped[str] = mapped_column(String(80), default="Candidatura enviada")
    applied_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    recruiter: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    job: Mapped[Job] = relationship(back_populates="application")

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default="Média")
    status: Mapped[str] = mapped_column(String(30), default="Pendente")
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    job: Mapped[Job | None] = relationship(back_populates="tasks")

class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("task_id", "recipient", "send_date", name="uq_task_recipient_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recipient: Mapped[str] = mapped_column(String(300))
    send_date: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentSettings(Base):
    """Configuração singleton (id=1) do agente de candidaturas."""
    __tablename__ = "agent_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=5)
    min_score: Mapped[int] = mapped_column(Integer, default=60)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ApplicationAttempt(Base):
    """Histórico de candidaturas. 'sent' só existe quando houve envio real ou confirmação explícita do usuário."""
    __tablename__ = "application_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    # prepared | awaiting_approval | manual_required | sent | failed | cancelled
    status: Mapped[str] = mapped_column(String(30), default="prepared")
    channel: Mapped[str] = mapped_column(String(30), default="manual")  # email | manual | manual_confirmed
    recipient: Mapped[str] = mapped_column(String(300), default="")
    subject: Mapped[str] = mapped_column(String(400), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    job: Mapped[Job] = relationship(back_populates="attempts")


class Skill(Base):
    """Catálogo canônico de competências e seus aliases."""
    __tablename__ = "market_skills"
    __table_args__ = (UniqueConstraint("canonical_name", name="uq_market_skill_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    taxonomy_version: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobSkill(Base):
    """Evidência rastreável de uma competência em uma vaga."""
    __tablename__ = "job_market_skills"
    __table_args__ = (
        UniqueConstraint("job_id", "skill_id", name="uq_job_market_skill"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("market_skills.id"), index=True)
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    evidence_field: Mapped[str] = mapped_column(String(30), default="description")
    extraction_method: Mapped[str] = mapped_column(String(30), default="dictionary")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    extractor_version: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketAnalysisRun(Base):
    """Snapshot imutável de uma execução de análise de mercado."""
    __tablename__ = "market_analysis_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    level_scope: Mapped[str] = mapped_column(String(20), default="both")
    area_scope: Mapped[str] = mapped_column(String(80), default="technology")
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    valid_jobs: Mapped[int] = mapped_column(Integer, default=0)
    jobs_with_description: Mapped[int] = mapped_column(Integer, default=0)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    taxonomy_version: Mapped[str] = mapped_column(String(30), default="")
    extractor_version: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(20), default="running")
    quality_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MarketSkillMetric(Base):
    """Métrica congelada de uma competência em um snapshot."""
    __tablename__ = "market_skill_metrics"
    __table_args__ = (UniqueConstraint("run_id", "skill_id", name="uq_run_market_skill"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("market_analysis_runs.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("market_skills.id"), index=True)
    jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    mention_rate: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)


class MarketSkillPair(Base):
    """Coocorrência congelada entre duas competências em um snapshot."""
    __tablename__ = "market_skill_pairs"
    __table_args__ = (
        UniqueConstraint("run_id", "skill_a_id", "skill_b_id", name="uq_run_market_skill_pair"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("market_analysis_runs.id", ondelete="CASCADE"), index=True)
    skill_a_id: Mapped[int] = mapped_column(ForeignKey("market_skills.id"))
    skill_b_id: Mapped[int] = mapped_column(ForeignKey("market_skills.id"))
    jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    pair_rate: Mapped[float] = mapped_column(Float, default=0.0)


class JobSkillExtraction(Base):
    """Registra que uma vaga foi processada, inclusive quando nenhuma competência foi encontrada."""
    __tablename__ = "job_skill_extractions"
    __table_args__ = (UniqueConstraint("job_id", name="uq_job_skill_extraction"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    extractor_version: Mapped[str] = mapped_column(String(30), default="")
    skills_found: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
