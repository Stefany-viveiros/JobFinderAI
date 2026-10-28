"""Execução única do agente (para agendadores). Respeita as configurações salvas no banco."""
from .agent import run_agent
from .db import SessionLocal, init_db


def main():
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
