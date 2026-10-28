"""Carrega o perfil profissional a partir de um JSON local e recalcula as compatibilidades.

Uso:  python -m jobfinder.load_profile perfil.local.json
O JSON contém dados pessoais: mantenha-o fora do Git (já ignorado por *.local.json).
"""
import json
import sys

from .api import ProfileUpdate
from .db import SessionLocal, init_db
from .service import get_profile, refresh_scores


def load_profile(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = ProfileUpdate(**json.load(fh)).model_dump()  # valida campos e tipos
    init_db()
    db = SessionLocal()
    try:
        profile = get_profile(db)
        for key, value in data.items():
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
