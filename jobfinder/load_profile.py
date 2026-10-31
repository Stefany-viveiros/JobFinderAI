"""Carrega o perfil profissional a partir de um JSON local e recalcula as compatibilidades.

Uso:  python -m jobfinder.load_profile perfil.local.json
O JSON contém dados pessoais: mantenha-o fora do Git (já ignorado por *.local.json).
"""
import json
import sys

from .api import ProfileUpdate, _sync_profile_records
from .db import SessionLocal, init_db
from .service import get_profile, refresh_scores
from .models import Education, Experience, Course, Certification, PortfolioProject


def load_profile(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = ProfileUpdate(**json.load(fh)).model_dump(exclude_none=True)  # valida campos e tipos
    init_db()
    db = SessionLocal()
    try:
        profile = get_profile(db)
        collections = {
            "educations": (Education, ("course", "institution", "degree", "status", "start_date", "end_date", "description")),
            "experiences": (Experience, ("company", "role", "employment_type", "location", "start_date", "end_date", "is_current", "description")),
            "courses": (Course, ("name", "provider", "workload", "completed_at", "status", "credential_url")),
            "certifications_items": (Certification, ("name", "issuer", "issued_at", "expires_at", "credential_id", "credential_url")),
            "portfolio_projects": (PortfolioProject, ("name", "description", "technologies", "repository_url", "demo_url", "status")),
        }
        for key, value in data.items():
            if key in collections:
                model, fields = collections[key]
                _sync_profile_records(getattr(profile, key), value, model, fields)
            else:
                setattr(profile, key, value)
        db.commit()
        refresh_scores(db)
        return data
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m jobfinder.load_profile perfil.local.json")
    loaded = load_profile(sys.argv[1])
    print(f"Perfil de {loaded['name']} carregado e compatibilidades recalculadas.")
