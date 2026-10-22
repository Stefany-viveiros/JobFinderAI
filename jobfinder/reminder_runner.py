"""One-shot daily reminder entry point; invoke from Windows Task Scheduler."""
from .db import init_db, SessionLocal
from .mailer import send_daily_reminder

def main():
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
