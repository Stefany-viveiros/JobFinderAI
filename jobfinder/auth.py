""""Autenticação por sessão opaca para o JobFinder AI.

O cookie contém um segredo aleatório; o banco armazena apenas seu SHA-256.
As rotas de escrita devem validar também o token CSRF via X-CSRF-Token.
"""
from datetime import datetime, timedelta
import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import User, UserSession
from .config import settings

SESSION_COOKIE = "jobfinder_session"
SESSION_HOURS = settings.session_hours
COOKIE_SECURE = settings.cookie_secure
# Frontend e API são hospedados em origens distintas. Em produção, o cookie
# precisa de SameSite=None para acompanhar fetch() com credentials="include".
# Em desenvolvimento HTTP local, mantém Lax porque navegadores exigem Secure
# quando SameSite=None.
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_auth_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_session(response: Response, db: Session, user: User) -> str:
    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id,
        token_hash=_hash(raw_token),
        csrf_token=csrf_token,
        expires_at=datetime.utcnow() + timedelta(hours=SESSION_HOURS),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=SESSION_HOURS * 3600,
        path="/",
    )
    response.headers["X-CSRF-Token"] = csrf_token
    return csrf_token


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )


def get_current_session(request: Request, db: Session = Depends(get_auth_db)):
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == _hash(raw_token),
            UserSession.expires_at > datetime.utcnow(),
        )
    )
    if not session or not session.user.is_active:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not secrets.compare_digest(supplied, session.csrf_token):
            raise HTTPException(status_code=403, detail="Validação CSRF inválida.")
    return session


def get_current_user(session: UserSession = Depends(get_current_session)) -> User:
    return session.user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito à administração.")
    return user
