from datetime import date, datetime
from email.message import EmailMessage
import smtplib
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .config import settings
from .models import Task, NotificationLog


def pending_tasks(db, today=None):
    today=today or date.today()
    return list(db.scalars(select(Task).where(Task.status!="Concluída",Task.notify.is_(True)).order_by(Task.due_date,Task.priority)).all())


def build_email(tasks, today=None):
    today=today or date.today()
    lines=[]
    for t in tasks:
        due=t.due_date.isoformat() if t.due_date else "Sem prazo"
        overdue=bool(t.due_date and t.due_date<today)
        lines.append(f"• {t.title} | Prazo: {due} | Prioridade: {t.priority}"+(" | VENCIDA" if overdue else ""))
    plain="Olá!\n\nVocê ainda tem tarefas pendentes no JobFinder AI:\n\n"+"\n".join(lines)+"\n\nAbra o JobFinder AI para atualizar suas tarefas.\n"
    html="<h2>JobFinder AI — tarefas pendentes</h2><ul>"+"".join(f"<li><b>{t.title}</b> — Prazo: {t.due_date.isoformat() if t.due_date else 'Sem prazo'} — Prioridade: {t.priority}"+(" <strong>(VENCIDA)</strong>" if t.due_date and t.due_date<today else "")+"</li>" for t in tasks)+"</ul><p>Abra o JobFinder AI para atualizar suas tarefas.</p>"
    return plain,html


def send_daily_reminder(db, now=None):
    now=now or datetime.now()
    recipient=settings.smtp_to.strip()
    tasks=pending_tasks(db,now.date())
    if not tasks: return {"status":"skipped","detail":"Nenhuma tarefa pendente configurada para notificação."}
    if not settings.smtp_ready or not settings.smtp_username or not settings.smtp_password:
        return {"status":"not_configured","detail":"SMTP incompleto. Configure SMTP_HOST, SMTP_FROM, SMTP_TO, SMTP_USERNAME e SMTP_PASSWORD."}
    # A chave diária por tarefa/destinatário evita repetir o mesmo lembrete para a mesma tarefa.
    eligible=[]
    for t in tasks:
        exists=db.scalar(select(NotificationLog).where(NotificationLog.task_id==t.id,NotificationLog.recipient==recipient,NotificationLog.send_date==now.date().isoformat(),NotificationLog.status=="sent"))
        if not exists: eligible.append(t)
    if not eligible: return {"status":"skipped","detail":"Lembretes de hoje já foram enviados para as tarefas pendentes."}
    msg=EmailMessage(); msg["Subject"]="JobFinder AI — Você ainda tem tarefas pendentes"; msg["From"]=settings.smtp_from; msg["To"]=recipient
    plain,html=build_email(eligible,now.date()); msg.set_content(plain); msg.add_alternative(html,subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=20) as server:
            server.ehlo()
            if settings.smtp_use_tls: server.starttls(); server.ehlo()
            server.login(settings.smtp_username,settings.smtp_password)
            server.send_message(msg)
        status="sent"; detail=f"Enviado para {recipient}; {len(eligible)} tarefa(s)."
    except Exception as exc:
        status="failed"; detail=f"{type(exc).__name__}: {exc}"
    for t in eligible:
        # failed attempts are logged separately; the unique key includes status? unique key is task/day,
        # so only insert a sent row after success; failures are stored with task_id NULL.
        if status=="sent":
            db.add(NotificationLog(task_id=t.id,recipient=recipient,send_date=now.date().isoformat(),status=status,detail=detail))
        else:
            db.add(NotificationLog(task_id=None,recipient=recipient,send_date=now.date().isoformat(),status=status,detail=f"Tarefa {t.id}: {detail}"))
    db.commit()
    return {"status":status,"detail":detail}
