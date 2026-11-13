"""Execução única do agente (para agendadores). Respeita as configurações salvas no banco."""
import os

from .agent import run_agent
from .db import SessionLocal, init_db


def main():
    # O runner legado não recebe identidade de usuário. Bloqueia antes de abrir
    # o banco ou coletar vagas enquanto o modo multiusuário estiver ativo.
    if os.getenv("MULTITENANT_READY", "false").lower() == "true":
        result = {
            "status": "blocked",
            "detail": "Agendador global desativado no modo multiusuário; configure execução individual por conta.",
        }
        print("JobFinder AI agent:", result)
        return result
    init_db()
    db = SessionLocal()
    try:
        result = run_agent(db)
    finally:
        db.close()
    print("JobFinder AI agent:", {k: v for k, v in result.items() if k != "errors"})
    for err in result["errors"]:
        print(" aviso:", err)
    return result


if __name__ == "__main__":
    main()
