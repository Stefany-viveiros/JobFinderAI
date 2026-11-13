"""One-shot daily reminder entry point; invoke from Windows Task Scheduler."""
import os

from .db import init_db, SessionLocal
from .mailer import send_daily_reminder

def main():
    # Bloqueia o runner legado antes de inicializar/migrar o banco.
    if os.getenv("MULTITENANT_READY", "false").lower() == "true":
        result = {
            "status": "blocked",
            "detail": "Agendador global de lembretes desativado no modo multiusuário; configure envio individual por conta.",
        }
        print(f"JobFinder AI reminder: {result['status']} — {result['detail']}")
        return result
    init_db()
    db=SessionLocal()
    try:
        result=send_daily_reminder(db)
    finally:
        db.close()
    print(f"JobFinder AI reminder: {result['status']} — {result['detail']}")
    if result["status"]=="failed": raise SystemExit(2)
    if result["status"]=="not_configured": raise SystemExit(3)
    return result

if __name__=="__main__": main()
