import streamlit as st
from datetime import date, datetime
from sqlalchemy import select, func
from .db import init_db, SessionLocal
from .models import Job, Application, Task, NotificationLog
from .service import get_profile, save_jobs, refresh_scores, create_task, complete_task, STATUSES
from .sources import SOURCES, collect_selected
from .mailer import pending_tasks, send_daily_reminder

st.set_page_config(page_title="JobFinder AI", page_icon="✦", layout="wide")
st.markdown("""<style>
:root{--navy:#101a36;--violet:#6d5ce8;--green:#dff4e7;--orange:#fff0dc}
.stApp{background:#f5f6fa;color:#172033}.block-container{max-width:1320px;padding-top:1.5rem}
[data-testid="stMetric"]{background:white;border:1px solid #e8eaf2;padding:16px;border-radius:16px}
.stButton>button{border-radius:10px;font-weight:600}.stTabs [data-baseweb="tab"]{font-weight:600}
.job-card{background:white;border:1px solid #e7e9f1;border-radius:16px;padding:18px;margin:8px 0}
.small-muted{color:#687187;font-size:.88rem}
</style>""",unsafe_allow_html=True)
init_db(); db=SessionLocal()

with st.sidebar:
    st.markdown("# ✦ JobFinder AI")
    st.caption("Seu espaço de busca e organização profissional")
    page=st.radio("Navegação",["Dashboard","Buscar vagas","Candidaturas","Tarefas","Perfil e configurações"])
    st.divider(); st.caption("Fontes públicas configuradas")
    st.caption("Remotive · Arbeitnow")

p=get_profile(db)

def task_form(job_id=None):
    with st.form("new_task_"+str(job_id)):
        title=st.text_input("Título da tarefa*"); desc=st.text_area("Descrição (opcional)")
        c1,c2,c3=st.columns(3)
        due=c1.date_input("Prazo",value=None)
        priority=c2.selectbox("Prioridade",["Baixa","Média","Alta","Urgente"])
        notify=c3.checkbox("Enviar lembrete por e-mail",True)
        if st.form_submit_button("Criar tarefa",type="primary"):
            if title.strip(): create_task(db,title,desc,due if due else None,priority,job_id,notify); st.success("Tarefa criada."); st.rerun()

if page=="Dashboard":
    st.title(f"Olá{', '+p.name if p.name else ''} 👋")
    st.write("Acompanhe suas oportunidades e as próximas ações.")
    total=db.scalar(select(func.count(Job.id)).where(Job.is_archived.is_(False))) or 0
    new=db.scalar(select(func.count(Job.id)).where(Job.is_archived.is_(False),Job.application.is_(None))) or 0
    saved=db.scalar(select(func.count(Job.id)).where(Job.is_favorite.is_(True),Job.is_archived.is_(False))) or 0
    apps=db.scalar(select(func.count(Application.id))) or 0
    interviews=db.scalar(select(func.count(Application.id)).where(Application.status=="Entrevista")) or 0
    pending=db.scalar(select(func.count(Task.id)).where(Task.status!="Concluída")) or 0
    overdue=db.scalar(select(func.count(Task.id)).where(Task.status!="Concluída",Task.due_date<date.today())) or 0
    cols=st.columns(4)
    for c,(label,val) in zip(cols,[("Vagas encontradas",total),("Novas oportunidades",new),("Vagas salvas",saved),("Candidaturas",apps)]): c.metric(label,val)
    cols=st.columns(4)
    cols[0].metric("Entrevistas",interviews); cols[1].metric("Tarefas pendentes",pending); cols[2].metric("Tarefas vencidas",overdue); cols[3].metric("Compatibilidade média",f"{(db.scalar(select(func.avg(Job.compatibility)).where(Job.is_archived.is_(False))) or 0):.0f}%")
    st.subheader("Próximos prazos")
    upcoming=list(db.scalars(select(Task).where(Task.status!="Concluída",Task.due_date.is_not(None)).order_by(Task.due_date).limit(6)).all())
    if upcoming:
        for t in upcoming: st.write(f"**{t.title}** · {t.due_date:%d/%m/%Y} · {t.priority}"+(" · VENCIDA" if t.due_date<date.today() else ""))
    else: st.info("Nenhuma tarefa com prazo cadastrada.")
    st.caption("Última busca: consulte a aba Buscar vagas. Lembretes SMTP: "+("configurado" if __import__('jobfinder.config',fromlist=['settings']).settings.smtp_ready else "precisa de configuração"))
    if st.button("＋ Criar tarefa rápida"): st.session_state.quick_task=True
    if st.session_state.get("quick_task"): task_form()

elif page=="Buscar vagas":
    st.title("Buscar oportunidades")
    st.write("Consulte fontes públicas. A cobertura de estágio brasileiro pode ser limitada, especialmente em fontes globais.")
    selected=st.multiselect("Fontes",list(SOURCES),default=list(SOURCES))
    if st.button("⟳ Buscar agora",type="primary"):
        with st.spinner("Consultando fontes..."):
            items,errors=collect_selected(selected); count=save_jobs(items); st.session_state.last_search=datetime.now().strftime("%d/%m/%Y %H:%M")
        st.success(f"Busca concluída: {len(items)} registros recebidos, {count} novas vagas salvas.")
        for e in errors: st.warning(e)
    with st.expander("Adicionar vaga manualmente"):
        with st.form("manual_job"):
            title=st.text_input("Título*"); company=st.text_input("Empresa"); url=st.text_input("Link original*"); location=st.text_input("Localização"); desc=st.text_area("Descrição")
            if st.form_submit_button("Salvar vaga"):
                if title and url:
                    count=save_jobs([{"source":"Manual","title":title,"company":company or "Empresa não informada","url":url,"location":location or "Não informada","description":desc,"modality":"Não informada","job_type":"Não informado","published_at":""}]); st.success("Vaga salva." if count else "Link já cadastrado."); st.rerun()
    st.divider()
    q=st.text_input("Pesquisar por título, empresa ou descrição")
    min_score=st.slider("Compatibilidade mínima",0,100,0,5)
    f1,f2,f3=st.columns(3); favorite=f1.checkbox("Somente favoritas"); modality=f2.selectbox("Modalidade",["Todas","Remoto","Híbrido","Presencial"]); sort=f3.selectbox("Ordenar por",["Compatibilidade","Mais recentes"])
    stmt=select(Job).where(Job.is_archived.is_(False),Job.compatibility>=min_score)
    if favorite: stmt=stmt.where(Job.is_favorite.is_(True))
    if modality!="Todas": stmt=stmt.where(Job.modality.ilike(f"%{modality}%"))
    if q: stmt=stmt.where((Job.title.ilike(f"%{q}%"))|(Job.company.ilike(f"%{q}%"))|(Job.description.ilike(f"%{q}%")))
    stmt=stmt.order_by(Job.compatibility.desc() if sort=="Compatibilidade" else Job.created_at.desc()).limit(100)
    jobs=list(db.scalars(stmt).all())
    st.caption(f"{len(jobs)} vaga(s) exibidas (máximo de 100 por consulta).")
    for j in jobs:
        with st.container(border=True):
            a,b=st.columns([5,1]); a.subheader(j.title); a.write(f"{j.company} · {j.location} · {j.modality} · {j.source}"); b.metric("Compatibilidade",f"{j.compatibility}%")
            if j.published_at: st.caption("Publicada: "+j.published_at)
            with st.expander("Ver detalhes e ações"):
                st.markdown(j.description[:12000] or "Descrição não fornecida",unsafe_allow_html=False)
                st.write("**Critérios atendidos**\n"+(j.match_reasons or "Não identificados")); st.write("**A verificar**\n"+(j.missing_reasons or "Nenhum alerta calculado"))
                st.link_button("Abrir vaga original",j.url)
                c1,c2,c3=st.columns(3)
                if c1.button("☆ Favoritar" if not j.is_favorite else "★ Desfavoritar",key=f"fav{j.id}"): j.is_favorite=not j.is_favorite; db.commit(); st.rerun()
                if c2.button("＋ Registrar candidatura",key=f"app{j.id}"):
                    if not j.application: db.add(Application(job_id=j.id,status="Candidatura enviada",applied_at=date.today())); db.commit(); st.success("Candidatura registrada."); st.rerun()
                if c3.button("＋ Criar tarefa",key=f"task{j.id}"): st.session_state["taskjob"]=j.id
                if st.session_state.get("taskjob")==j.id: task_form(j.id)

elif page=="Candidaturas":
    st.title("Minhas candidaturas")
    apps=list(db.scalars(select(Application).order_by(Application.updated_at.desc())).all())
    if not apps: st.info("Você ainda não registrou candidaturas. Salve uma vaga e use Registrar candidatura.")
    for a in apps:
        j=a.job
        with st.container(border=True):
            st.subheader(j.title); st.caption(j.company+" · "+j.url)
            with st.form(f"application{a.id}"):
                status=st.selectbox("Etapa",STATUSES,index=STATUSES.index(a.status) if a.status in STATUSES else 0)
                c1,c2=st.columns(2); applied=c1.date_input("Data da candidatura",value=a.applied_at); deadline=c2.date_input("Prazo",value=a.deadline)
                recruiter=st.text_input("Recrutador (opcional)",a.recruiter); notes=st.text_area("Notas",a.notes)
                if st.form_submit_button("Salvar acompanhamento"):
                    a.status=status; a.applied_at=applied if applied else None; a.deadline=deadline if deadline else None; a.recruiter=recruiter; a.notes=notes; db.commit(); st.success("Atualizado."); st.rerun()

elif page=="Tarefas":
    st.title("Tarefas e prazos")
    task_form()
    view=st.segmented_control("Visualização",["Pendentes","Concluídas","Vencidas","Todas"],default="Pendentes")
    stmt=select(Task).order_by(Task.due_date,Task.priority)
    if view=="Pendentes": stmt=stmt.where(Task.status!="Concluída")
    elif view=="Concluídas": stmt=stmt.where(Task.status=="Concluída")
    elif view=="Vencidas": stmt=stmt.where(Task.status!="Concluída",Task.due_date<date.today())
    tasks=list(db.scalars(stmt).all())
    for t in tasks:
        with st.container(border=True):
            c1,c2=st.columns([5,1]); c1.markdown(f"**{t.title}**"); c1.caption(f"{t.due_date or 'Sem prazo'} · {t.priority} · {'Concluída' if t.status=='Concluída' else 'Pendente'}"+(f" · Vaga: {t.job.title}" if t.job else ""))
            if t.description: c1.write(t.description)
            if t.status!="Concluída" and c2.button("Concluir",key=f"done{t.id}"): complete_task(db,t); st.rerun()
            with st.expander("Editar tarefa"):
                with st.form(f"edit_task{t.id}"):
                    title=st.text_input("Título",t.title); description=st.text_area("Descrição",t.description); due=st.date_input("Prazo",value=t.due_date); priority=st.selectbox("Prioridade",["Baixa","Média","Alta","Urgente"],index=["Baixa","Média","Alta","Urgente"].index(t.priority) if t.priority in ["Baixa","Média","Alta","Urgente"] else 1); notify=st.checkbox("Lembrete por e-mail",t.notify); done=st.checkbox("Concluída",t.status=="Concluída")
                    if st.form_submit_button("Salvar tarefa"):
                        t.title=title; t.description=description; t.due_date=due if due else None; t.priority=priority; t.notify=notify; t.status="Concluída" if done else "Pendente"; t.completed_at=datetime.now() if done else None; db.commit(); st.rerun()
                if st.button("Excluir tarefa",key=f"del{t.id}"):
                    st.session_state["delete_task"]=t.id
                if st.session_state.get("delete_task")==t.id:
                    st.warning("Confirma excluir esta tarefa?")
                    if st.button("Confirmar exclusão",key=f"confirmdel{t.id}"): db.delete(t); db.commit(); st.session_state.pop("delete_task",None); st.rerun()
    st.divider(); st.subheader("Lembretes")
    from .config import settings
    st.info("SMTP: "+("configurado" if settings.smtp_ready and settings.smtp_username and settings.smtp_password else "não configurado"))
    if st.button("Testar/enviar resumo agora"):
        result=send_daily_reminder(db); st.write(result)
    logs=list(db.scalars(select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(20)).all())
    if logs:
        st.caption("Histórico recente")
        for log in logs: st.write(f"{log.created_at:%d/%m %H:%M} · {log.status} · {log.detail}")

elif page=="Perfil e configurações":
    st.title("Perfil profissional e configurações")
    st.caption("Campos opcionais. Cadastre apenas informações verdadeiras; a compatibilidade será recalculada com base no que você informar.")
    with st.form("profile"):
        name=st.text_input("Nome ou identificação",p.name); course=st.text_input("Curso/área",p.course); institution=st.text_input("Instituição",p.institution); stage=st.text_input("Semestre/etapa",p.academic_stage)
        tech=st.text_area("Tecnologias (separe por vírgula)",p.technologies); skills=st.text_area("Habilidades técnicas",p.skills); experience=st.text_area("Experiência (opcional)",p.experience); projects=st.text_area("Projetos",p.projects); certs=st.text_area("Certificações",p.certifications)
        keywords=st.text_area("Palavras-chave",p.keywords); interests=st.text_input("Áreas de interesse (separe por vírgula)",p.interests); location=st.text_input("Localização desejada",p.location); modality=st.text_input("Modalidades (Remoto, Híbrido, Presencial)",p.modality); types=st.text_input("Tipos de oportunidade",p.job_types); excludes=st.text_input("Termos a excluir (separe por vírgula)",p.exclude_terms)
        st.markdown("**Pesos de compatibilidade** (valores relativos; serão normalizados)")
        c=st.columns(5); wk=c[0].number_input("Palavras-chave",0,100,p.weight_keywords); wa=c[1].number_input("Área",0,100,p.weight_area); wm=c[2].number_input("Modalidade",0,100,p.weight_modality); wl=c[3].number_input("Localização",0,100,p.weight_location); we=c[4].number_input("Nível",0,100,p.weight_level)
        if st.form_submit_button("Salvar perfil",type="primary"):
            vals=locals()
            for field,value in [("name",name),("course",course),("institution",institution),("academic_stage",stage),("technologies",tech),("skills",skills),("experience",experience),("projects",projects),("certifications",certs),("keywords",keywords),("interests",interests),("location",location),("modality",modality),("job_types",types),("exclude_terms",excludes),("weight_keywords",wk),("weight_area",wa),("weight_modality",wm),("weight_location",wl),("weight_level",we)]: setattr(p,field,value)
            db.commit(); refresh_scores(db); st.success("Perfil salvo e compatibilidades recalculadas."); st.rerun()
    st.divider(); st.subheader("E-mail e execução diária")
    from .config import settings
    st.write("Status SMTP: "+("configuração básica detectada" if settings.smtp_ready else "pendente"))
    st.code("SMTP_HOST=\nSMTP_PORT=587\nSMTP_USERNAME=\nSMTP_PASSWORD=\nSMTP_FROM=\nSMTP_TO=\nSMTP_USE_TLS=true\nTIMEZONE=America/Sao_Paulo",language="dotenv")
    st.caption("Edite o arquivo .env na pasta do projeto. Nunca compartilhe esse arquivo nem o publique no GitHub.")
    st.write("Para configurar o Agendador do Windows, consulte README.md e scripts/instalar_agendador.ps1.")

db.close()
