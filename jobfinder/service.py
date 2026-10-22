from datetime import date, datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import SessionLocal
from .models import Job, Profile, Task, Application
from .matching import score_job

STATUSES=["Nova oportunidade","Salva","Candidatura enviada","Teste técnico","Entrevista","Aprovada","Reprovada","Encerrada"]

def get_profile(db):
    p=db.get(Profile,1)
    if not p: p=Profile(id=1); db.add(p); db.commit(); db.refresh(p)
    return p

def save_jobs(items):
    added=0; db=SessionLocal()
    try:
        p=get_profile(db)
        for item in items:
            url=(item.get("url") or "").strip()
            if not url: continue
            existing=db.scalar(select(Job).where(Job.url==url))
            if existing: continue
            score, reasons, missing=score_job(item,p)
            j=Job(**{k:item.get(k) for k in ["source","source_id","title","company","description","location","modality","job_type","published_at","url"]}, compatibility=score, match_reasons="\n".join(reasons), missing_reasons="\n".join(missing))
            db.add(j)
            try: db.commit(); added+=1
            except IntegrityError: db.rollback()
        return added
    finally: db.close()

def refresh_scores(db):
    p=get_profile(db)
    for j in db.scalars(select(Job)).all():
        s,r,m=score_job({"title":j.title,"description":j.description,"location":j.location,"modality":j.modality},p)
        j.compatibility=s; j.match_reasons="\n".join(r); j.missing_reasons="\n".join(m)
    db.commit()

def create_task(db, title, description="", due_date=None, priority="Média", job_id=None, notify=True):
    t=Task(title=title.strip(),description=description,due_date=due_date,priority=priority,job_id=job_id,notify=notify)
    db.add(t); db.commit(); db.refresh(t); return t

def complete_task(db, task):
    task.status="Concluída"; task.completed_at=datetime.utcnow(); db.commit()


def prepare_ranked_items(items, profile, existing_urls=(), limit=80):
    """Remove duplicatas e prioriza vagas compatíveis com o perfil."""
    existing = {
        str(url or "").strip().lower().rstrip("/")
        for url in existing_urls
        if url
    }
    seen = set()
    candidates = []
    duplicates = 0

    for item in items:
        url = str(item.get("url") or "").strip()

        if not url:
            continue

        key = url.lower().rstrip("/")

        if key in seen or key in existing:
            duplicates += 1
            continue

        seen.add(key)

        score, reasons, missing = score_job(item, profile)

        candidates.append({
            "item": item,
            "score": score,
            "reasons": reasons,
            "missing": missing,
        })

    candidates.sort(
        key=lambda candidate: (
            candidate["score"],
            str(candidate["item"].get("published_at") or ""),
        ),
        reverse=True,
    )

    safe_limit = max(1, min(80, int(limit)))

    return candidates[:safe_limit], duplicates, len(candidates)


def collect_and_save_ranked(items, limit=80):
    """Classifica as vagas, elimina duplicatas e salva as melhores."""
    db = SessionLocal()

    try:
        profile = get_profile(db)
        existing_urls = db.scalars(select(Job.url)).all()

        ranked, duplicates, eligible = prepare_ranked_items(
            items,
            profile,
            existing_urls,
            limit,
        )

        saved = 0
        highest_compatibility = None

        for candidate in ranked:
            item = candidate["item"]

            job = Job(
                **{
                    key: item.get(key)
                    for key in [
                        "source",
                        "source_id",
                        "title",
                        "company",
                        "description",
                        "location",
                        "modality",
                        "job_type",
                        "published_at",
                        "url",
                    ]
                },
                compatibility=candidate["score"],
                match_reasons="\n".join(candidate["reasons"]),
                missing_reasons="\n".join(candidate["missing"]),
            )

            db.add(job)

            try:
                db.commit()
                saved += 1

                if highest_compatibility is None:
                    highest_compatibility = candidate["score"]

            except IntegrityError:
                db.rollback()
                duplicates += 1

        return {
            "saved": saved,
            "duplicates": duplicates,
            "eligible": eligible,
            "limit": max(1, min(80, int(limit))),
            "highest_compatibility": highest_compatibility,
        }

    finally:
        db.close()
