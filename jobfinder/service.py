from datetime import date, datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import SessionLocal
from .models import Job, JobMatch, Profile, Task, Application
from .matching import score_job
from .filters import normalize_url, dedupe_key, classify_level

STATUSES=["Nova oportunidade","Salva","Candidatura enviada","Teste técnico","Entrevista","Aprovada","Reprovada","Encerrada"]

def get_profile(db, user_id=None):
    """Retorna perfil do usuário; sem user_id, mantém compatibilidade apenas para rotinas legadas internas."""
    if user_id is None:
        p = db.get(Profile, 1)
        if not p:
            p = Profile(id=1)
            db.add(p); db.commit(); db.refresh(p)
        return p
    p = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if p is None:
        p = Profile(user_id=user_id)
        db.add(p); db.commit(); db.refresh(p)
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
            j=Job(**{k:item.get(k) for k in ["source","source_id","title","company","description","location","modality","job_type","published_at","url"]}, compatibility=score, match_reasons="\n".join(reasons), missing_reasons="\n".join(missing),
                  level=classify_level(item.get("title"),item.get("description"),item.get("job_type")) or "outro",
                  dedupe_key=dedupe_key(item.get("title"),item.get("company")))
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

def create_task(db, title, description="", due_date=None, priority="Média", job_id=None, notify=True, user_id=None):
    t=Task(user_id=user_id,title=title.strip(),description=description,due_date=due_date,priority=priority,job_id=job_id,notify=notify)
    db.add(t); db.commit(); db.refresh(t); return t

def complete_task(db, task):
    task.status="Concluída"; task.completed_at=datetime.utcnow(); db.commit()


_JOB_FIELDS = ["source", "source_id", "title", "company", "description", "location",
               "modality", "job_type", "published_at", "url"]


def _rank(items, profile, existing_urls=(), existing_keys=(), limit=80, only_target=False):
    """Deduplica (URL normalizada e título+empresa), filtra estágio/júnior e ordena por compatibilidade."""
    from .filters import is_target_job

    seen_urls = {normalize_url(u) for u in existing_urls if u}
    seen_keys = {k for k in existing_keys if k}
    candidates, duplicates, filtered_out = [], 0, 0

    for item in items:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        url_key = normalize_url(url)
        title_key = dedupe_key(item.get("title"), item.get("company"))
        if url_key in seen_urls or (title_key and title_key in seen_keys):
            duplicates += 1
            continue
        if only_target and not is_target_job(item):
            filtered_out += 1
            continue
        seen_urls.add(url_key)
        if title_key:
            seen_keys.add(title_key)
        score, reasons, missing = score_job(item, profile)
        candidates.append({"item": item, "score": score, "reasons": reasons, "missing": missing,
                           "dedupe_key": title_key})

    candidates.sort(key=lambda c: (c["score"], str(c["item"].get("published_at") or "")), reverse=True)
    safe_limit = max(1, min(80, int(limit)))
    return {"ranked": candidates[:safe_limit], "duplicates": duplicates,
            "eligible": len(candidates), "filtered_out": filtered_out}


def prepare_ranked_items(items, profile, existing_urls=(), limit=80, existing_keys=(), only_target=False):
    """Remove duplicatas e prioriza vagas compatíveis com o perfil."""
    r = _rank(items, profile, existing_urls, existing_keys, limit, only_target)
    return r["ranked"], r["duplicates"], r["eligible"]


def collect_and_save_ranked(items, limit=80, only_target=True):
    """Classifica, elimina duplicatas, mantém só estágio/júnior de tecnologia e salva as melhores."""
    db = SessionLocal()
    try:
        profile = get_profile(db)
        existing_urls = db.scalars(select(Job.url)).all()
        existing_keys = db.scalars(select(Job.dedupe_key).where(Job.dedupe_key.is_not(None))).all()
        r = _rank(items, profile, existing_urls, existing_keys, limit, only_target)

        saved, duplicates, highest = 0, r["duplicates"], None
        for candidate in r["ranked"]:
            item = candidate["item"]
            job = Job(**{k: item.get(k) for k in _JOB_FIELDS},
                      compatibility=candidate["score"],
                      match_reasons="\n".join(candidate["reasons"]),
                      missing_reasons="\n".join(candidate["missing"]),
                      level=classify_level(item.get("title"), item.get("description"), item.get("job_type")) or "outro",
                      dedupe_key=candidate["dedupe_key"])
            db.add(job)
            try:
                db.commit()
                saved += 1
                if highest is None:
                    highest = candidate["score"]
            except IntegrityError:
                db.rollback()
                duplicates += 1

        return {"saved": saved, "duplicates": duplicates, "eligible": r["eligible"],
                "filtered_out": r["filtered_out"], "limit": max(1, min(80, int(limit))),
                "highest_compatibility": highest}
    finally:
        db.close()


def collect_for_user(db, items, user_id, limit=80, only_target=True):
    """Salva vagas no catálogo compartilhado e calcula compatibilidade privada do usuário."""
    from .filters import is_target_job
    if user_id is None:
        raise ValueError("Coleta SaaS exige usuário autenticado.")
    profile = get_profile(db, user_id=user_id)
    received_ids, duplicates, filtered_out = [], 0, 0
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        title_key = dedupe_key(item.get("title"), item.get("company"))
        if only_target and not is_target_job(item):
            filtered_out += 1
            continue
        job = db.scalar(select(Job).where(Job.url == url))
        if job is None and title_key:
            job = db.scalar(select(Job).where(Job.dedupe_key == title_key))
        if job is None:
            job = Job(**{k: item.get(k) for k in _JOB_FIELDS},
                      level=classify_level(item.get("title"), item.get("description"), item.get("job_type")) or "outro",
                      dedupe_key=title_key)
            db.add(job)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                job = db.scalar(select(Job).where(Job.url == url))
                if job is None:
                    duplicates += 1
                    continue
        else:
            duplicates += 1
        received_ids.append(job.id)
    ranked = []
    for job_id in dict.fromkeys(received_ids):
        job = db.get(Job, job_id)
        if job is None:
            continue
        score, reasons, missing = score_job({
            "title": job.title, "description": job.description,
            "location": job.location, "modality": job.modality,
            "job_type": job.job_type,
        }, profile)
        ranked.append((score, job_id, reasons, missing))
    ranked.sort(key=lambda row: row[0], reverse=True)
    saved_matches = 0
    for score, job_id, reasons, missing in ranked[:max(1, min(80, int(limit)))]:
        match = db.scalar(select(JobMatch).where(
            JobMatch.user_id == user_id, JobMatch.job_id == job_id
        ))
        if match is None:
            match = JobMatch(user_id=user_id, job_id=job_id)
            db.add(match)
        match.compatibility = score
        match.match_reasons = "\n".join(reasons)
        match.missing_reasons = "\n".join(missing)
        saved_matches += 1
    db.commit()
    return {
        "saved": saved_matches, "duplicates": duplicates,
        "eligible": len(ranked), "filtered_out": filtered_out,
        "limit": max(1, min(80, int(limit))),
        "highest_compatibility": ranked[0][0] if ranked else None,
    }
