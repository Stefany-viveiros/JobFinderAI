import { useCallback, useEffect, useMemo, useState } from 'react'
import AgentPage, { AttemptPill } from './AgentPage.jsx'
import {
  Activity, Bot, ArrowDownRight, ArrowUpRight, Bell, BriefcaseBusiness, CalendarDays,
  Check, CheckCircle2, ChevronDown, CircleHelp, Clock3, ExternalLink, Filter,
  LayoutDashboard, LoaderCircle, LogOut, Menu, Plus, Search, Send, Settings,
  SlidersHorizontal, Sparkles, Star, Target, Trash2, UserRound, X, Zap,
} from 'lucide-react'

const API = 'http://127.0.0.1:8000/api'
const STATUS = ['Nova oportunidade', 'Salva', 'Candidatura enviada', 'Teste técnico', 'Entrevista', 'Aprovada', 'Reprovada', 'Encerrada']
const emptyJob = { title: '', company: '', url: '', location: '', description: '' }
const emptyTask = { title: '', description: '', due_date: '', priority: 'Média', notify: true }
const emptyProfile = {
  name: '', course: '', institution: '', academic_stage: '', technologies: '', skills: '', experience: '', projects: '', certifications: '', keywords: '', interests: 'Estágio em Tecnologia', location: '', modality: 'Remoto, Híbrido, Presencial', job_types: 'Estágio, Júnior', exclude_terms: '', weight_keywords: 40, weight_area: 25, weight_modality: 15, weight_location: 10, weight_level: 10,
}

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || body.message || `Erro ${res.status}`)
  return body
}
const datePt = (d) => d ? new Date(`${d.slice(0, 10)}T12:00:00`).toLocaleDateString('pt-BR') : 'Sem prazo'
const initials = (name) => (name || 'JF').trim().split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase()

function App() {
  const [page, setPage] = useState('Dashboard')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [dashboard, setDashboard] = useState(null)
  const [jobs, setJobs] = useState([])
  const [applications, setApplications] = useState([])
  const [tasks, setTasks] = useState([])
  const [notificationHistory, setNotificationHistory] = useState([])
  const [profile, setProfile] = useState(emptyProfile)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [modal, setModal] = useState('')
  const [query, setQuery] = useState('')
  const [minScore, setMinScore] = useState(0)
  const [favoriteOnly, setFavoriteOnly] = useState(false)
  const [modality, setModality] = useState('Todas')
  const [sort, setSort] = useState('Compatibilidade')
  const [taskView, setTaskView] = useState('Pendentes')
  const [jobForm, setJobForm] = useState(emptyJob)
  const [taskForm, setTaskForm] = useState(emptyTask)
  const [editingTask, setEditingTask] = useState(null)
  const [editingApp, setEditingApp] = useState(null)
  const [appForm, setAppForm] = useState({})
  const [sourceSelection, setSourceSelection] = useState(['Remotive', 'Arbeitnow', 'OkEmprego', 'Nerdin'])
  const [levelFilter, setLevelFilter] = useState('alvo')
  const [sourceFilter, setSourceFilter] = useState('Todas')
  const [attemptFilter, setAttemptFilter] = useState('todas')
  const [attempts, setAttempts] = useState([])
  const [agentSettings, setAgentSettings] = useState({ auto_apply_enabled: false, require_approval: true, daily_limit: 5, min_score: 60, profile_ready: true })
  const [agentRun, setAgentRun] = useState(null)
  const [sourcesInfo, setSourcesInfo] = useState(null)

  const notify = useCallback((message, type = 'success') => {
    setNotice({ message, type })
    window.clearTimeout(notify.timeout)
    notify.timeout = window.setTimeout(() => setNotice(null), 4200)
  }, [])

  const loadDashboard = useCallback(async () => setDashboard(await api('/dashboard')), [])
  const loadJobs = useCallback(async () => {
    const params = new URLSearchParams({ q: query, min_score: String(minScore), favorite: String(favoriteOnly), modality, sort, level: levelFilter, source: sourceFilter, attempt_status: attemptFilter, limit: '250' })
    setJobs(await api(`/jobs?${params}`))
  }, [query, minScore, favoriteOnly, modality, sort, levelFilter, sourceFilter, attemptFilter])
  const loadApps = useCallback(async () => setApplications(await api('/applications')), [])
  const loadTasks = useCallback(async (view = taskView) => setTasks(await api(`/tasks?view=${encodeURIComponent(view)}`)), [taskView])
  const loadProfile = useCallback(async () => setProfile({ ...emptyProfile, ...(await api('/profile')) }), [])
  const loadAttempts = useCallback(async () => setAttempts(await api('/attempts')), [])
  const loadAgent = useCallback(async () => setAgentSettings(await api('/agent/settings')), [])
  const loadSources = useCallback(async () => setSourcesInfo(await api('/sources')), [])
  const loadNotifications = useCallback(async () => setNotificationHistory(await api('/notifications')), [])

  const refreshCurrent = useCallback(async () => {
    setLoading(true)
    try {
      await Promise.all([loadDashboard(), loadJobs(), loadApps(), loadTasks(), loadProfile(), loadNotifications(), loadAttempts(), loadAgent(), loadSources()])
    } catch (e) { notify(`Não foi possível conectar à API: ${e.message}. Confira se o backend está iniciado.`, 'error') }
    finally { setLoading(false) }
  }, [loadDashboard, loadJobs, loadApps, loadTasks, loadProfile, loadNotifications, loadAttempts, loadAgent, loadSources, notify])

  useEffect(() => { refreshCurrent() }, [])
  useEffect(() => { if (page === 'Buscar vagas') loadJobs().catch(e => notify(e.message, 'error')) }, [page, loadJobs])
  useEffect(() => { if (page === 'Tarefas') loadTasks(taskView).catch(e => notify(e.message, 'error')) }, [page, taskView])

  const changePage = (next) => { setPage(next); setSidebarOpen(false) }
  const doAction = async (action, success) => {
    setBusy(true)
    try { await action(); await Promise.all([loadDashboard(), loadJobs(), loadApps(), loadTasks(), loadNotifications(), loadAttempts(), loadAgent()]); notify(success) }
    catch (e) { notify(e.message, 'error') }
    finally { setBusy(false) }
  }

  async function collectJobs() {
    setBusy(true)
    try {
      const result = await api('/jobs/collect', { method: 'POST', body: JSON.stringify({ sources: sourceSelection, limit: 80 }) })
      await Promise.all([loadDashboard(), loadJobs(), loadApps(), loadTasks(), loadNotifications(), loadAttempts()])
      const warnings = result.errors?.length ? ` Avisos: ${result.errors.join(' · ')}` : ''
      notify(`Busca concluída: ${result.received} registros recebidos, ${result.filtered_out ?? 0} fora do perfil (nível/área), ${result.eligible ?? 0} elegíveis, ${result.saved} salvas e ${result.duplicates ?? 0} duplicadas.${warnings}`, result.errors?.length ? 'error' : 'success')
    } catch (e) { notify(e.message, 'error') }
    finally { setBusy(false) }
  }

  async function saveJob(e) {
    e.preventDefault()
    await doAction(async () => {
      const result = await api('/jobs', { method: 'POST', body: JSON.stringify(jobForm) })
      setModal(''); setJobForm(emptyJob); await loadJobs(); notify(result.message)
    }, 'Vaga salva.')
  }

  async function toggleFavorite(id) {
    await doAction(() => api(`/jobs/${id}/favorite`, { method: 'PATCH' }), 'Favoritos atualizados.')
  }
  async function applyJob(id) {
    if (!window.confirm('Registrar como ENVIADA? Confirme apenas se você já enviou a candidatura no site da vaga.')) return
    await doAction(() => api(`/jobs/${id}/apply`, { method: 'POST', body: JSON.stringify({ confirmed: true }) }), 'Candidatura registrada como enviada (confirmação manual).')
  }
  async function prepareJob(id) {
    await doAction(async () => { const r = await api(`/jobs/${id}/prepare`, { method: 'POST' }); notify(r.message) }, 'Candidatura preparada.')
  }
  async function saveAgentSettings() {
    await doAction(async () => { const r = await api('/agent/settings', { method: 'PUT', body: JSON.stringify({ auto_apply_enabled: agentSettings.auto_apply_enabled, require_approval: agentSettings.require_approval, daily_limit: agentSettings.daily_limit, min_score: agentSettings.min_score }) }); setAgentSettings(r.settings) }, 'Configurações do agente salvas.')
  }
  async function runAgent() {
    setBusy(true)
    try {
      const r = await api('/agent/run', { method: 'POST', body: JSON.stringify({ sources: sourceSelection, limit: 80 }) })
      setAgentRun(r)
      await Promise.all([loadDashboard(), loadJobs(), loadAttempts(), loadAgent()])
      notify(r.message || `Agente concluído: ${r.saved} vagas salvas, ${r.awaiting_approval + r.manual_required + r.prepared} candidaturas preparadas, ${r.sent} enviadas, ${r.failed} falhas.`, r.errors?.length || r.failed ? 'error' : 'success')
    } catch (e) { notify(e.message, 'error') } finally { setBusy(false) }
  }
  async function approveAttempt(id) {
    setBusy(true)
    try { const r = await api(`/attempts/${id}/approve`, { method: 'POST' }); await Promise.all([loadDashboard(), loadJobs(), loadAttempts(), loadAgent(), loadApps()]); notify(r.message, r.attempt.status === 'sent' ? 'success' : 'error') }
    catch (e) { notify(e.message, 'error') } finally { setBusy(false) }
  }
  async function cancelAttempt(id) {
    await doAction(() => api(`/attempts/${id}/cancel`, { method: 'POST' }), 'Candidatura cancelada.')
  }
  async function saveTask(e) {
    e.preventDefault()
    await doAction(async () => {
      if (editingTask) {
        await api(`/tasks/${editingTask.id}`, { method: 'PUT', body: JSON.stringify({ ...taskForm, due_date: taskForm.due_date || null, status: editingTask.status || 'Pendente' }) })
      } else {
        await api('/tasks', { method: 'POST', body: JSON.stringify({ ...taskForm, due_date: taskForm.due_date || null, job_id: editingTask?.job_id || null }) })
      }
      setModal(''); setEditingTask(null); setTaskForm(emptyTask); await loadTasks()
    }, editingTask ? 'Tarefa atualizada.' : 'Tarefa criada.')
  }
  async function completeTask(id) {
    await doAction(() => api(`/tasks/${id}/complete`, { method: 'PATCH' }), 'Tarefa concluída.')
  }
  async function deleteTask(id) {
    if (!window.confirm('Deseja excluir esta tarefa?')) return
    await doAction(() => api(`/tasks/${id}`, { method: 'DELETE' }), 'Tarefa excluída.')
  }
  async function saveApplication(e) {
    e.preventDefault()
    await doAction(async () => {
      await api(`/applications/${editingApp.id}`, { method: 'PUT', body: JSON.stringify({ ...appForm, applied_at: appForm.applied_at || null, deadline: appForm.deadline || null }) })
      setModal(''); setEditingApp(null); await loadApps()
    }, 'Candidatura atualizada.')
  }
  async function sendReminders() {
    setBusy(true)
    try {
      const result = await api('/notifications/send', { method: 'POST' })
      await loadNotifications()
      const detail = result.result?.detail || 'Solicitação processada.'
      notify(detail, result.result?.status === 'failed' ? 'error' : 'success')
    } catch (e) { notify(e.message, 'error') }
    finally { setBusy(false) }
  }
  async function saveProfile(e) {
    e.preventDefault()
    await doAction(async () => { const result = await api('/profile', { method: 'PUT', body: JSON.stringify(profile) }); setProfile(result.profile || profile); await loadJobs() }, 'Perfil salvo e compatibilidades recalculadas.')
  }

  const metrics = dashboard?.metrics || {}
  const pageLabel = { Dashboard: 'Visão geral', 'Buscar vagas': 'Buscar oportunidades', Candidaturas: 'Minhas candidaturas', Agente: 'Agente de candidaturas', Tarefas: 'Tarefas e prazos', 'Perfil e configurações': 'Perfil profissional' }[page]
  const todayText = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })

  return <div className="app-shell">
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><Sparkles size={21}/></div><div><div className="brand-name">jobfinder<span>AI</span></div><div className="brand-sub">CAREER WORKSPACE</div></div><button className="icon-btn sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Fechar menu"><X size={19}/></button></div>
      <div className="workspace-label">WORKSPACE</div>
      <nav className="nav-list">
        <NavItem icon={LayoutDashboard} text="Visão geral" active={page === 'Dashboard'} onClick={() => changePage('Dashboard')} />
        <NavItem icon={Search} text="Buscar vagas" active={page === 'Buscar vagas'} onClick={() => changePage('Buscar vagas')} count={metrics.new_jobs} />
        <NavItem icon={Bot} text="Agente" active={page === 'Agente'} onClick={() => changePage('Agente')} count={metrics.awaiting_approval} />
        <NavItem icon={BriefcaseBusiness} text="Candidaturas" active={page === 'Candidaturas'} onClick={() => changePage('Candidaturas')} />
        <NavItem icon={CheckCircle2} text="Tarefas" active={page === 'Tarefas'} onClick={() => changePage('Tarefas')} count={metrics.pending_tasks} />
      </nav>
      <div className="workspace-label nav-spacer">PREFERÊNCIAS</div>
      <nav className="nav-list"><NavItem icon={UserRound} text="Perfil profissional" active={page === 'Perfil e configurações'} onClick={() => changePage('Perfil e configurações')} /><NavItem icon={Settings} text="Configurações" active={false} onClick={() => changePage('Perfil e configurações')} /></nav>
      <div className="sidebar-bottom">
        <div className="upgrade-card"><div className="upgrade-icon"><Zap size={17}/></div><strong>Seu próximo passo</strong><p>Mantenha seu perfil atualizado para melhorar a compatibilidade das vagas.</p><button onClick={() => changePage('Perfil e configurações')}>Completar perfil <ArrowUpRight size={14}/></button></div>
        <div className="user-card"><div className="avatar">{initials(profile.name)}</div><div className="user-info"><strong>{profile.name || 'Seu perfil'}</strong><span>{profile.course || 'Candidata a tecnologia'}</span></div><button className="icon-btn user-settings" onClick={() => changePage('Perfil e configurações')} aria-label="Editar perfil"><Settings size={17}/></button></div>
      </div>
    </aside>
    {sidebarOpen && <button className="mobile-scrim" onClick={() => setSidebarOpen(false)} aria-label="Fechar menu"/>}
    <main className="main-area">
      <header className="topbar"><div className="topbar-left"><button className="icon-btn mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Abrir menu"><Menu size={21}/></button><div className="breadcrumb">Workspace <span>/</span> <strong>{pageLabel}</strong></div></div><div className="topbar-right"><span className="today-label"><CalendarDays size={15}/>{todayText}</span><button className="icon-btn notification-btn" onClick={() => changePage('Tarefas')} title="Ver tarefas"><Bell size={19}/>{metrics.overdue_tasks > 0 && <i/>}</button><div className="top-avatar">{initials(profile.name)}</div></div></header>
      <div className="content-wrap">
        {loading && !dashboard ? <div className="loading-panel"><LoaderCircle className="spin" size={25}/><span>Carregando seu workspace...</span></div> : <>
          {page === 'Dashboard' && <DashboardPage dashboard={dashboard} jobs={jobs} onNavigate={changePage} onCreateTask={() => { setEditingTask(null); setTaskForm(emptyTask); setModal('task') }} onFavorite={toggleFavorite} />}
          {page === 'Buscar vagas' && <JobsPage jobs={jobs} query={query} setQuery={setQuery} minScore={minScore} setMinScore={setMinScore} favoriteOnly={favoriteOnly} setFavoriteOnly={setFavoriteOnly} modality={modality} setModality={setModality} sort={sort} setSort={setSort} onCollect={collectJobs} sourceSelection={sourceSelection} setSourceSelection={setSourceSelection} busy={busy} onAdd={() => setModal('job')} onFavorite={toggleFavorite} onApply={applyJob} onPrepare={prepareJob} levelFilter={levelFilter} setLevelFilter={setLevelFilter} sourceFilter={sourceFilter} setSourceFilter={setSourceFilter} attemptFilter={attemptFilter} setAttemptFilter={setAttemptFilter} />}
          {page === 'Agente' && <AgentPage settings={agentSettings} setSettings={setAgentSettings} onSave={saveAgentSettings} onRun={runAgent} runResult={agentRun} attempts={attempts} sources={sourcesInfo} onApprove={approveAttempt} onCancel={cancelAttempt} onConfirmManual={applyJob} busy={busy} />}
          {page === 'Candidaturas' && <ApplicationsPage applications={applications} onEdit={(a) => { setEditingApp(a); setAppForm({ status: a.status, applied_at: a.applied_at || '', deadline: a.deadline || '', recruiter: a.recruiter || '', notes: a.notes || '' }); setModal('application') }} />}
          {page === 'Tarefas' && <TasksPage tasks={tasks} view={taskView} setView={setTaskView} onCreate={() => { setEditingTask(null); setTaskForm(emptyTask); setModal('task') }} onEdit={(t) => { setEditingTask(t); setTaskForm({ title: t.title, description: t.description || '', due_date: t.due_date || '', priority: t.priority, notify: t.notify }); setModal('task') }} onComplete={completeTask} onDelete={deleteTask} onSendReminders={sendReminders} smtpReady={Boolean(dashboard?.smtp_ready)} notificationHistory={notificationHistory} busy={busy} />}
          {page === 'Perfil e configurações' && <ProfilePage profile={profile} setProfile={setProfile} onSave={saveProfile} busy={busy} />}
        </>}
      </div>
      <footer className="footer"><span>© {new Date().getFullYear()} JobFinder AI</span><span><span className="status-dot"/> Seus dados ficam armazenados localmente <CircleHelp size={14}/></span></footer>
    </main>
    {notice && <div className={`toast ${notice.type}`}><span className="toast-symbol">{notice.type === 'error' ? <CircleHelp size={18}/> : <CheckCircle2 size={18}/>}</span><span>{notice.message}</span><button className="icon-btn" onClick={() => setNotice(null)}><X size={16}/></button></div>}
    {modal && <Modal title={modal === 'job' ? 'Adicionar oportunidade' : modal === 'task' ? (editingTask ? 'Editar tarefa' : 'Nova tarefa') : 'Atualizar candidatura'} onClose={() => { setModal(''); setEditingTask(null); setEditingApp(null) }}>
      {modal === 'job' && <form className="modal-form" onSubmit={saveJob}><Field label="Título da vaga *"><input autoFocus required value={jobForm.title} onChange={e => setJobForm({ ...jobForm, title: e.target.value })} placeholder="Ex.: Estágio em desenvolvimento"/></Field><Field label="Empresa"><input value={jobForm.company} onChange={e => setJobForm({ ...jobForm, company: e.target.value })} placeholder="Nome da empresa"/></Field><Field label="Link original *"><input required type="url" value={jobForm.url} onChange={e => setJobForm({ ...jobForm, url: e.target.value })} placeholder="https://..."/></Field><Field label="Localização"><input value={jobForm.location} onChange={e => setJobForm({ ...jobForm, location: e.target.value })} placeholder="São Paulo, remoto..."/></Field><Field label="Descrição"><textarea rows="4" value={jobForm.description} onChange={e => setJobForm({ ...jobForm, description: e.target.value })} placeholder="Responsabilidades, requisitos, tecnologias..."/></Field><ModalActions busy={busy} onCancel={() => setModal('')} submit="Salvar oportunidade"/></form>}
      {modal === 'task' && <form className="modal-form" onSubmit={saveTask}><Field label="Título da tarefa *"><input autoFocus required value={taskForm.title} onChange={e => setTaskForm({ ...taskForm, title: e.target.value })} placeholder="Ex.: Preparar currículo para a vaga"/></Field><Field label="Descrição"><textarea rows="3" value={taskForm.description} onChange={e => setTaskForm({ ...taskForm, description: e.target.value })} placeholder="Detalhes ou próximos passos"/></Field><div className="form-grid"><Field label="Prazo"><input type="date" value={taskForm.due_date} onChange={e => setTaskForm({ ...taskForm, due_date: e.target.value })}/></Field><Field label="Prioridade"><select value={taskForm.priority} onChange={e => setTaskForm({ ...taskForm, priority: e.target.value })}>{['Baixa','Média','Alta','Urgente'].map(x => <option key={x}>{x}</option>)}</select></Field></div><label className="check-row"><input type="checkbox" checked={taskForm.notify} onChange={e => setTaskForm({ ...taskForm, notify: e.target.checked })}/> Lembrete por e-mail (requer SMTP)</label><ModalActions busy={busy} onCancel={() => setModal('')} submit={editingTask ? 'Salvar alterações' : 'Criar tarefa'}/></form>}
      {modal === 'application' && <form className="modal-form" onSubmit={saveApplication}><div className="modal-context"><strong>{editingApp?.job?.title}</strong><span>{editingApp?.job?.company}</span></div><Field label="Etapa atual"><select value={appForm.status || STATUS[0]} onChange={e => setAppForm({ ...appForm, status: e.target.value })}>{STATUS.map(s => <option key={s}>{s}</option>)}</select></Field><div className="form-grid"><Field label="Data da candidatura"><input type="date" value={appForm.applied_at || ''} onChange={e => setAppForm({ ...appForm, applied_at: e.target.value })}/></Field><Field label="Prazo"><input type="date" value={appForm.deadline || ''} onChange={e => setAppForm({ ...appForm, deadline: e.target.value })}/></Field></div><Field label="Recrutador"><input value={appForm.recruiter || ''} onChange={e => setAppForm({ ...appForm, recruiter: e.target.value })} placeholder="Nome (opcional)"/></Field><Field label="Notas"><textarea rows="4" value={appForm.notes || ''} onChange={e => setAppForm({ ...appForm, notes: e.target.value })} placeholder="Informações da conversa, próximos passos..."/></Field><ModalActions busy={busy} onCancel={() => setModal('')} submit="Salvar acompanhamento"/></form>}
    </Modal>}
  </div>
}

function NavItem({ icon: Icon, text, active, onClick, count }) { return <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}><Icon size={18}/><span>{text}</span>{Number(count) > 0 && <small>{count > 99 ? '99+' : count}</small>}</button> }
function SectionHeading({ eyebrow, title, subtitle, children }) { return <div className="section-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{children && <div className="heading-actions">{children}</div>}</div> }
function MetricCard({ label, value, hint, icon: Icon, tone = 'violet', trend }) { return <div className="metric-card"><div className={`metric-icon ${tone}`}><Icon size={19}/></div><div className="metric-title">{label}</div><div className="metric-value">{value ?? 0}</div><div className="metric-foot">{trend && <span className="metric-trend"><ArrowUpRight size={13}/>{trend}</span>}<span>{hint}</span></div></div> }
function DashboardPage({ dashboard, jobs, onNavigate, onCreateTask, onFavorite }) {
  const m = dashboard?.metrics || {}
  const upcoming = dashboard?.upcoming_tasks || []
  const topJobs = dashboard?.recent_jobs || []
  return <>
    <SectionHeading eyebrow="SEU PAINEL DE CARREIRA" title={`Olá${dashboard?.profile_name ? `, ${dashboard.profile_name.split(' ')[0]}` : ''} 👋`} subtitle="Um lugar para encontrar oportunidades e avançar na sua carreira." ><button className="btn btn-secondary" onClick={onCreateTask}><Plus size={16}/> Nova tarefa</button><button className="btn btn-primary" onClick={() => onNavigate('Buscar vagas')}><Search size={16}/> Explorar vagas</button></SectionHeading>
    <div className="welcome-strip"><div className="welcome-symbol"><Sparkles size={22}/></div><div className="welcome-copy"><strong>Pequenos passos constroem grandes oportunidades.</strong><span>Revise suas candidaturas e priorize a próxima ação do dia.</span></div><div className="welcome-side"><span>COMPATIBILIDADE MÉDIA</span><strong>{m.average_compatibility || 0}%</strong></div></div>
    <div className="metric-grid five"><MetricCard label="Vagas encontradas" value={m.total_jobs} hint={`${m.target_jobs || 0} estágio/júnior`} icon={BriefcaseBusiness} tone="violet"/><MetricCard label="Vagas compatíveis" value={m.compatible_jobs} hint={`estágio/júnior ≥ ${m.min_score ?? 60}%`} icon={Target} tone="blue"/><MetricCard label="Candidaturas enviadas" value={m.sent_applications} hint={`${m.sent_automatically || 0} automática(s) · ${m.sent_manually_confirmed || 0} confirmada(s) por você`} icon={Send} tone="green"/><MetricCard label="Candidaturas pendentes" value={m.pending_applications} hint={`${m.awaiting_approval || 0} aguardando aprovação`} icon={Clock3} tone="amber"/><MetricCard label="Candidaturas com falha" value={m.failed_applications} hint="envio recusado ou com erro" icon={Activity} tone="violet"/></div>
    <div className="dashboard-grid"><section className="panel recent-panel"><div className="panel-heading"><div><h2>Oportunidades recentes</h2><p>Vagas adicionadas à sua busca</p></div><button className="text-action" onClick={() => onNavigate('Buscar vagas')}>Ver todas <ArrowUpRight size={15}/></button></div>{topJobs.length ? <div className="recent-list">{topJobs.map(j => <JobRow key={j.id} job={j} compact onFavorite={() => onFavorite(j.id)}/>)}</div> : <EmptyState icon={Search} title="Sua próxima oportunidade começa aqui" text="Busque novas vagas ou adicione uma oportunidade manualmente." action={<button className="btn btn-primary btn-sm" onClick={() => onNavigate('Buscar vagas')}>Buscar vagas</button>}/>}</section>
      <section className="panel upcoming-panel"><div className="panel-heading"><div><h2>Próximos prazos</h2><p>O que precisa da sua atenção</p></div><button className="circle-action" onClick={onCreateTask} title="Criar tarefa"><Plus size={17}/></button></div>{upcoming.length ? <div className="timeline">{upcoming.map((t, i) => <div className="timeline-item" key={t.id}><div className={`timeline-dot ${t.due_date && t.due_date < new Date().toISOString().slice(0,10) ? 'overdue' : ''}`}><CalendarDays size={14}/></div><div className="timeline-copy"><strong>{t.title}</strong><span>{datePt(t.due_date)} · {t.priority}</span>{t.due_date && t.due_date < new Date().toISOString().slice(0,10) && <em>Prazo vencido</em>}</div></div>)}</div> : <EmptyState icon={CalendarDays} title="Agenda livre por enquanto" text="Crie uma tarefa para organizar seu próximo passo." action={<button className="text-action" onClick={onCreateTask}>Adicionar tarefa <Plus size={14}/></button>}/>}<div className="task-summary"><div><span className="summary-icon"><Activity size={16}/></span><span>Tarefas pendentes</span></div><strong>{m.pending_tasks || 0}</strong></div>{(m.overdue_tasks || 0) > 0 && <div className="overdue-note"><Clock3 size={15}/>{m.overdue_tasks} tarefa(s) vencida(s)</div>}<button className="panel-footer-link" onClick={() => onNavigate('Tarefas')}>Abrir minhas tarefas <ArrowUpRight size={15}/></button></section>
    </div>
    <div className="bottom-insight"><div className="insight-icon"><Target size={20}/></div><div><strong>Seu perfil influencia a compatibilidade</strong><span>Adicione tecnologias, habilidades e áreas de interesse para calcular uma pontuação mais útil.</span></div><button className="text-action" onClick={() => onNavigate('Perfil e configurações')}>Revisar perfil <ArrowUpRight size={15}/></button></div>
  </>
}
function JobsPage({ jobs, query, setQuery, minScore, setMinScore, favoriteOnly, setFavoriteOnly, modality, setModality, sort, setSort, onCollect, sourceSelection, setSourceSelection, busy, onAdd, onFavorite, onApply, onPrepare, levelFilter, setLevelFilter, sourceFilter, setSourceFilter, attemptFilter, setAttemptFilter }) {
  const [showSources, setShowSources] = useState(false)
  return <><SectionHeading eyebrow="DESCUBRA SEU PRÓXIMO PASSO" title="Buscar oportunidades" subtitle="Encontre vagas, compare a compatibilidade e organize suas candidaturas."><button className="btn btn-secondary" onClick={onAdd}><Plus size={16}/> Adicionar manualmente</button><button className="btn btn-primary" onClick={onCollect} disabled={busy}><span className={busy ? 'spin-wrap' : ''}>{busy ? <LoaderCircle size={16}/> : <Search size={16}/>}</span> Buscar agora</button></SectionHeading>
    <div className="search-banner"><div className="search-banner-icon"><Sparkles size={19}/></div><div><strong>Encontre vagas alinhadas ao seu perfil</strong><span>Busque nas fontes públicas configuradas ou use os filtros para refinar sua lista.</span></div><button className="banner-tune" onClick={() => setShowSources(!showSources)}><SlidersHorizontal size={15}/> Fontes</button></div>
    {showSources && <div className="source-picker">{['Remotive', 'Arbeitnow', 'OkEmprego', 'Nerdin'].map(s => <label key={s} className="check-row"><input type="checkbox" checked={sourceSelection.includes(s)} onChange={e => setSourceSelection(e.target.checked ? [...sourceSelection, s] : sourceSelection.filter(x => x !== s))}/>{s}</label>)}<span className="muted small">Indeed e Vagas.com não permitem coleta automática: veja os links na página Agente. Só vagas de estágio/júnior em tecnologia são salvas.</span></div>}
    <div className="panel job-filter-panel"><div className="search-input-wrap"><Search size={18}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar por cargo, empresa ou tecnologia..."/><kbd>Buscar</kbd></div><div className="filter-row"><label className="filter-control"><span>Compatibilidade mínima</span><div className="range-field"><input type="range" min="0" max="100" step="5" value={minScore} onChange={e => setMinScore(Number(e.target.value))}/><strong>{minScore}%</strong></div></label><label className="filter-control"><span>Modalidade</span><select value={modality} onChange={e => setModality(e.target.value)}><option>Todas</option><option>Remoto</option><option>Híbrido</option><option>Presencial</option></select></label><label className="filter-control"><span>Ordenar por</span><select value={sort} onChange={e => setSort(e.target.value)}><option>Compatibilidade</option><option>Mais recentes</option></select></label><label className="filter-control"><span>Nível</span><select value={levelFilter} onChange={e => setLevelFilter(e.target.value)}><option value="alvo">Estágio + Júnior (tecnologia)</option><option value="estagio">Estágio</option><option value="junior">Júnior</option><option value="todas">Todas as vagas salvas</option></select></label><label className="filter-control"><span>Fonte</span><select value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}>{['Todas', 'Remotive', 'Arbeitnow', 'OkEmprego', 'Nerdin', 'Manual'].map(x => <option key={x}>{x}</option>)}</select></label><label className="filter-control"><span>Candidatura</span><select value={attemptFilter} onChange={e => setAttemptFilter(e.target.value)}><option value="todas">Todas</option><option value="sem_tentativa">Sem candidatura</option><option value="awaiting_approval">Aguardando aprovação</option><option value="manual_required">Finalizar manualmente</option><option value="sent">Enviadas</option><option value="failed">Com falha</option></select></label><label className="favorite-filter"><input type="checkbox" checked={favoriteOnly} onChange={e => setFavoriteOnly(e.target.checked)}/><Star size={16}/> Favoritas</label></div></div>
    <div className="list-toolbar"><div><strong>{jobs.length}</strong> oportunidade(s) encontradas <span>· Até 250 resultados</span></div><div className="toolbar-status"><span className="status-dot"/>Pontuação explicável</div></div>
    {jobs.length ? <div className="job-results">{jobs.map(j => <JobCard key={j.id} job={j} onFavorite={() => onFavorite(j.id)} onApply={() => onApply(j.id)} onPrepare={() => onPrepare(j.id)}/>)}</div> : <div className="panel"><EmptyState icon={Filter} title="Nenhuma vaga com esses filtros" text="Tente reduzir a compatibilidade mínima ou remover algum filtro." action={<button className="btn btn-secondary btn-sm" onClick={() => {setQuery('');setMinScore(0);setFavoriteOnly(false);setModality('Todas');setLevelFilter('todas');setSourceFilter('Todas');setAttemptFilter('todas')}}>Limpar filtros</button>}/></div>}
  </>
}
function JobRow({ job, compact = false, onFavorite }) { return <div className="recent-job"><div className="company-avatar">{initials(job.company)}</div><div className="recent-job-copy"><strong>{job.title}</strong><span>{job.company} <i>·</i> {job.location || 'Local não informado'}</span></div><div className={`score-mini ${job.compatibility >= 70 ? 'score-good' : job.compatibility >= 40 ? 'score-mid' : 'score-low'}`}>{job.compatibility}%</div>{onFavorite && <button className={`tiny-star ${job.is_favorite ? 'selected' : ''}`} onClick={onFavorite} title="Favoritar"><Star size={16} fill={job.is_favorite ? 'currentColor' : 'none'}/></button>}</div> }
function JobCard({ job, onFavorite, onApply, onPrepare }) {
  const [expanded, setExpanded] = useState(false)
  const reasons = (job.match_reasons || '').split('\n').filter(Boolean)
  const missing = (job.missing_reasons || '').split('\n').filter(Boolean)
  return <article className="job-card"><div className="job-card-main"><div className="company-avatar job-company-avatar">{initials(job.company)}</div><div className="job-title-wrap"><div className="job-title-line"><h3>{job.title}</h3>{job.is_favorite && <span className="saved-badge"><Star size={12} fill="currentColor"/> Salva</span>}</div><div className="job-company-line">{job.company} <span>·</span> {job.location || 'Local não informado'}</div><div className="job-tags"><span><BriefcaseBusiness size={13}/>{job.job_type || 'Tipo não informado'}</span><span><Activity size={13}/>{job.modality || 'Modalidade não informada'}</span><span className="source-tag">{job.source}</span>{job.level && job.level !== 'outro' && <span className="level-tag">{job.level === 'estagio' ? 'Estágio' : 'Júnior'}</span>}{job.latest_attempt && <AttemptPill status={job.latest_attempt.status}/>}</div></div><div className="compatibility-block"><div className={`compatibility-ring ${job.compatibility >= 70 ? 'ring-good' : job.compatibility >= 40 ? 'ring-mid' : 'ring-low'}`}><strong>{job.compatibility}%</strong></div><span>compatibilidade</span></div></div>
    <div className="score-track"><div style={{ width: `${job.compatibility}%` }} className={job.compatibility >= 70 ? 'fill-good' : job.compatibility >= 40 ? 'fill-mid' : 'fill-low'}/></div>
    {expanded && <div className="job-details"><div className="description-text">{job.description ? <p>{job.description.replace(/<[^>]*>/g, ' ').slice(0, 6000)}</p> : <p className="muted">Descrição não fornecida pela fonte.</p>}</div><div className="match-columns"><div><strong className="match-title good"><CheckCircle2 size={15}/> Critérios encontrados</strong>{reasons.length ? <ul>{reasons.map((r,i) => <li key={i}>{r}</li>)}</ul> : <p className="muted small">Nenhum critério identificado.</p>}</div><div><strong className="match-title warn"><CircleHelp size={15}/> Pontos a verificar</strong>{missing.length ? <ul>{missing.map((r,i) => <li key={i}>{r}</li>)}</ul> : <p className="muted small">Nenhum alerta calculado.</p>}</div></div></div>}
    <div className="job-card-actions"><button className="text-action" onClick={() => setExpanded(!expanded)}>{expanded ? 'Ocultar detalhes' : 'Ver detalhes'} <ChevronDown size={14} className={expanded ? 'rotate-180' : ''}/></button><div className="job-action-right"><button className={`icon-btn favorite-action ${job.is_favorite ? 'selected' : ''}`} onClick={onFavorite} title={job.is_favorite ? 'Remover dos favoritos' : 'Favoritar'}><Star size={17} fill={job.is_favorite ? 'currentColor' : 'none'}/></button>{job.application ? <span className="application-status"><Check size={14}/>{job.application.status}</span> : <>{!job.latest_attempt && <button className="btn btn-secondary btn-sm" onClick={onPrepare}><Bot size={14}/> Preparar candidatura</button>}<button className="btn btn-secondary btn-sm" onClick={onApply} title="Use somente depois de enviar no site da vaga"><Check size={14}/> Já enviei</button></>}<a href={job.url} target="_blank" rel="noreferrer" className="btn btn-primary btn-sm">Abrir vaga <ExternalLink size={14}/></a></div></div>
  </article>
}
function ApplicationsPage({ applications, onEdit }) {
  const [filter, setFilter] = useState('Todas')
  const shown = useMemo(() => applications.filter(a => filter === 'Todas' || a.status === filter), [applications, filter])
  return <><SectionHeading eyebrow="ACOMPANHE SEU PROGRESSO" title="Minhas candidaturas" subtitle="Registre cada etapa para não perder o fio da sua busca."/><div className="app-stats-row"><div className="app-stat"><span>Total de candidaturas</span><strong>{applications.length}</strong></div><div className="app-stat"><span>Entrevistas</span><strong>{applications.filter(a => a.status === 'Entrevista').length}</strong></div><div className="app-stat"><span>Em andamento</span><strong>{applications.filter(a => !['Aprovada','Reprovada','Encerrada'].includes(a.status)).length}</strong></div><div className="app-stat"><span>Aprovadas</span><strong>{applications.filter(a => a.status === 'Aprovada').length}</strong></div></div><div className="panel applications-panel"><div className="panel-heading"><div><h2>Pipeline de candidaturas</h2><p>Atualize a etapa sempre que houver uma novidade</p></div><select className="compact-select" value={filter} onChange={e => setFilter(e.target.value)}><option>Todas</option>{STATUS.map(s => <option key={s}>{s}</option>)}</select></div>{shown.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Oportunidade</th><th>Etapa</th><th>Data de envio</th><th>Prazo</th><th></th></tr></thead><tbody>{shown.map(a => <tr key={a.id}><td><div className="table-job"><div className="company-avatar small-avatar">{initials(a.job?.company)}</div><div><strong>{a.job?.title}</strong><span>{a.job?.company}</span></div></div></td><td><StatusPill status={a.status}/></td><td>{datePt(a.applied_at)}</td><td>{datePt(a.deadline)}</td><td><button className="btn btn-secondary btn-sm" onClick={() => onEdit(a)}>Atualizar <ChevronDown size={13}/></button></td></tr>)}</tbody></table></div> : <EmptyState icon={BriefcaseBusiness} title="Sua jornada começa com uma candidatura" text="Candidaturas enviadas (pelo agente ou confirmadas por você) aparecem aqui para acompanhar cada etapa."/>}</div></>
}
function StatusPill({ status }) { const cls = status === 'Entrevista' ? 'purple' : status === 'Aprovada' ? 'green' : ['Reprovada','Encerrada'].includes(status) ? 'gray' : status === 'Teste técnico' ? 'blue' : 'amber'; return <span className={`status-pill ${cls}`}><i/>{status}</span> }
function TasksPage({ tasks, view, setView, onCreate, onEdit, onComplete, onDelete, onSendReminders, smtpReady, notificationHistory, busy }) {
  const views = ['Pendentes','Concluídas','Vencidas','Todas']
  return <><SectionHeading eyebrow="ORGANIZAÇÃO E FOCO" title="Tarefas e prazos" subtitle="Transforme cada candidatura em próximos passos claros."><button className="btn btn-primary" onClick={onCreate}><Plus size={16}/> Nova tarefa</button></SectionHeading><div className="task-overview"><div className="task-overview-icon"><CheckCircle2 size={20}/></div><div><strong>Um passo de cada vez</strong><span>Defina prazos realistas e priorize o que vai aproximar você da próxima oportunidade.</span></div><strong className="task-overview-count">{tasks.filter(t => t.status !== 'Concluída').length}<small>visíveis pendentes</small></strong></div><div className="task-tabs">{views.map(v => <button key={v} className={view === v ? 'active' : ''} onClick={() => setView(v)}>{v}</button>)}</div>{tasks.length ? <div className="task-list">{tasks.map(t => <article className={`task-card ${t.status === 'Concluída' ? 'completed' : ''}`} key={t.id}><button className={`task-check ${t.status === 'Concluída' ? 'checked' : ''}`} onClick={() => t.status !== 'Concluída' && onComplete(t.id)} aria-label="Concluir tarefa">{t.status === 'Concluída' && <Check size={15}/>}</button><div className="task-main"><div className="task-title-row"><h3>{t.title}</h3><PriorityPill priority={t.priority}/></div>{t.description && <p>{t.description}</p>}<div className="task-meta"><span><CalendarDays size={14}/>{datePt(t.due_date)}</span>{t.job_title && <span><BriefcaseBusiness size={14}/>{t.job_title}</span>}{t.notify && <span><Bell size={13}/>Lembrete ativado</span>}{t.due_date && t.due_date < new Date().toISOString().slice(0,10) && t.status !== 'Concluída' && <span className="overdue-text">Prazo vencido</span>}</div></div><div className="task-actions"><button className="icon-btn" onClick={() => onEdit(t)} title="Editar"><Settings size={16}/></button><button className="icon-btn delete-action" onClick={() => onDelete(t.id)} title="Excluir"><Trash2 size={16}/></button></div></article>)}</div> : <div className="panel"><EmptyState icon={CheckCircle2} title="Tudo em dia por aqui" text="Não encontramos tarefas nesta visualização. Você pode adicionar uma nova tarefa a qualquer momento." action={<button className="btn btn-primary btn-sm" onClick={onCreate}><Plus size={14}/> Criar tarefa</button>}/></div>}<div className="reminder-note"><Bell size={17}/><div><strong>Lembretes por e-mail</strong><span>{smtpReady ? 'SMTP detectado. O botão envia um resumo das tarefas pendentes para o destinatário configurado.' : <>Configure SMTP no arquivo <code>.env</code> antes de enviar lembretes.</>}</span></div><button className="btn btn-secondary btn-sm" onClick={onSendReminders} disabled={busy || !smtpReady}>{busy ? <LoaderCircle size={14} className="spin"/> : <Send size={14}/>} Enviar resumo</button></div>{notificationHistory?.length > 0 && <section className="panel notification-panel"><div className="panel-heading"><div><h2>Histórico de lembretes</h2><p>Últimas tentativas registradas</p></div></div><div className="notification-list">{notificationHistory.slice(0,8).map(log => <div className="notification-row" key={log.id}><span className={`notification-status ${log.status === 'sent' ? 'sent' : 'failed'}`}>{log.status === 'sent' ? 'Enviado' : log.status}</span><span className="notification-detail">{log.detail}</span><time>{log.created_at ? new Date(log.created_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : ''}</time></div>)}</div></section>}</>
}
function PriorityPill({ priority }) { const c = priority === 'Urgente' ? 'urgent' : priority === 'Alta' ? 'high' : priority === 'Baixa' ? 'low' : 'medium'; return <span className={`priority-pill ${c}`}><i/>{priority}</span> }
function ProfilePage({ profile, setProfile, onSave, busy }) {
  const [importing, setImporting] = useState(false)
  const [importMessage, setImportMessage] = useState('')
  const [importError, setImportError] = useState('')
  const set = (field, value) => setProfile(p => ({ ...p, [field]: value }))
  async function importResume(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!/\\.(pdf|docx)$/i.test(file.name)) { setImportError('Selecione um arquivo PDF ou DOCX.'); return }
    if (file.size > 5 * 1024 * 1024) { setImportError('O arquivo deve ter no máximo 5 MB.'); return }
    const form = new FormData()
    form.append('file', file)
    setImporting(true); setImportError(''); setImportMessage('')
    try {
      const response = await fetch(`${API}/profile/import`, { method: 'POST', body: form })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || `Erro ${response.status}`)
      setProfile(current => ({ ...current, ...body.extracted }))
      setImportMessage('Informações extraídas. Revise os campos preenchidos e clique em “Salvar perfil”.')
    } catch (error) { setImportError(error.message || 'Não foi possível importar o currículo.') }
    finally { setImporting(false) }
  }
  return <><SectionHeading eyebrow="PERSONALIZE SUA BUSCA" title="Perfil profissional" subtitle="Informe suas experiências e interesses reais. A pontuação das vagas é recalculada ao salvar."/><section className="panel resume-import-panel"><div className="resume-import-copy"><div className="resume-import-icon"><Sparkles size={19}/></div><div><strong>Preencher com meu currículo</strong><p>Envie um PDF ou DOCX. O JobFinder AI sugere os dados encontrados para você revisar antes de salvar.</p></div></div><label className="btn btn-secondary resume-upload-button">{importing ? <LoaderCircle size={16} className="spin"/> : <UserRound size={16}/>} {importing ? 'Analisando currículo...' : 'Selecionar currículo'}<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={importResume} disabled={importing} hidden/></label>{importMessage && <p className="resume-import-success"><CheckCircle2 size={15}/>{importMessage}</p>}{importError && <p className="resume-import-error">{importError}</p>}<small>Limite de 5 MB. O arquivo é processado para extração e não é armazenado. Nada é salvo no perfil até você clicar em “Salvar perfil”.</small></section><form className="profile-form" onSubmit={onSave}><div className="profile-header-card"><div className="profile-large-avatar">{initials(profile.name)}</div><div><strong>{profile.name || 'Seu nome'}</strong><span>{profile.course || 'Área profissional'}{profile.institution ? ` · ${profile.institution}` : ''}</span><p>Este perfil é usado localmente para comparar vagas com seus interesses e conhecimentos.</p></div><div className="profile-status"><span className="status-dot"/>Perfil editável</div></div><div className="profile-grid"><section className="panel profile-panel"><div className="profile-panel-title"><div className="form-section-icon"><UserRound size={17}/></div><div><h2>Informações profissionais</h2><p>Contexto da sua formação</p></div></div><div className="form-grid"><Field label="Nome ou identificação"><input value={profile.name || ''} onChange={e => set('name', e.target.value)} placeholder="Seu nome"/></Field><Field label="Curso / área"><input value={profile.course || ''} onChange={e => set('course', e.target.value)} placeholder="Ex.: Engenharia da Computação"/></Field><Field label="Instituição"><input value={profile.institution || ''} onChange={e => set('institution', e.target.value)} placeholder="Faculdade ou instituição"/></Field><Field label="Semestre / etapa"><input value={profile.academic_stage || ''} onChange={e => set('academic_stage', e.target.value)} placeholder="Ex.: 5º semestre"/></Field><Field label="Localização desejada"><input value={profile.location || ''} onChange={e => set('location', e.target.value)} placeholder="Ex.: São Paulo, SP"/></Field><Field label="Modalidades aceitas"><input value={profile.modality || ''} onChange={e => set('modality', e.target.value)} placeholder="Remoto, Híbrido, Presencial"/></Field></div></section><section className="panel profile-panel"><div className="profile-panel-title"><div className="form-section-icon blue"><Zap size={17}/></div><div><h2>Conhecimentos e objetivos</h2><p>Usados no cálculo de compatibilidade</p></div></div><Field label="Tecnologias (separadas por vírgula)"><textarea rows="2" value={profile.technologies || ''} onChange={e => set('technologies', e.target.value)} placeholder="Python, JavaScript, React, SQL..."/></Field><Field label="Habilidades técnicas"><textarea rows="2" value={profile.skills || ''} onChange={e => set('skills', e.target.value)} placeholder="APIs REST, Git, análise de dados..."/></Field><Field label="Palavras-chave"><textarea rows="2" value={profile.keywords || ''} onChange={e => set('keywords', e.target.value)} placeholder="Palavras que aparecem nas vagas de interesse"/></Field><Field label="Áreas de interesse"><input value={profile.interests || ''} onChange={e => set('interests', e.target.value)} placeholder="Estágio em Tecnologia, Backend, Dados..."/></Field><Field label="Tipos de oportunidade"><input value={profile.job_types || ''} onChange={e => set('job_types', e.target.value)} placeholder="Estágio, Júnior"/></Field><Field label="Termos a excluir"><input value={profile.exclude_terms || ''} onChange={e => set('exclude_terms', e.target.value)} placeholder="Termos separados por vírgula (opcional)"/></Field></section><section className="panel profile-panel"><div className="profile-panel-title"><div className="form-section-icon green"><BriefcaseBusiness size={17}/></div><div><h2>Experiência e portfólio</h2><p>Conteúdos opcionais para seu perfil</p></div></div><Field label="Experiência"><textarea rows="3" value={profile.experience || ''} onChange={e => set('experience', e.target.value)} placeholder="Descreva experiências reais de trabalho ou estudos"/></Field><Field label="Projetos"><textarea rows="3" value={profile.projects || ''} onChange={e => set('projects', e.target.value)} placeholder="Projetos acadêmicos e pessoais"/></Field><Field label="Certificações"><textarea rows="2" value={profile.certifications || ''} onChange={e => set('certifications', e.target.value)} placeholder="Cursos e certificações"/></Field></section><section className="panel profile-panel weights-panel"><div className="profile-panel-title"><div className="form-section-icon amber"><Target size={17}/></div><div><h2>Critérios de compatibilidade</h2><p>Pesos relativos que ajudam a calcular a pontuação</p></div></div>{[['weight_keywords','Palavras-chave'],['weight_area','Área de interesse'],['weight_modality','Modalidade'],['weight_location','Localização'],['weight_level','Nível da vaga']].map(([key,label]) => <div className="weight-row" key={key}><div><span>{label}</span><strong>{profile[key] ?? 0}</strong></div><input type="range" min="0" max="100" value={profile[key] ?? 0} onChange={e => set(key, Number(e.target.value))}/></div>)}<p className="weight-tip">Os pesos são normalizados no cálculo. A pontuação é uma estimativa explicável, não uma previsão de contratação.</p></section></div><div className="profile-save-bar"><span>As alterações recalculam as compatibilidades das vagas cadastradas.</span><button type="submit" className="btn btn-primary" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin"/> : <Check size={16}/>} Salvar perfil</button></div></form></>
}
function Field({ label, children }) { return <label className="field"><span>{label}</span>{children}</label> }
function Modal({ title, children, onClose }) { useEffect(() => { const f = e => e.key === 'Escape' && onClose(); document.addEventListener('keydown', f); document.body.style.overflow = 'hidden'; return () => {document.removeEventListener('keydown',f);document.body.style.overflow = ''} }, [onClose]); return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="modal"><div className="modal-header"><div><span className="eyebrow">JOBFINDER AI</span><h2>{title}</h2></div><button className="icon-btn" onClick={onClose} aria-label="Fechar"><X size={20}/></button></div>{children}</div></div> }
function ModalActions({ busy, onCancel, submit }) { return <div className="modal-actions"><button type="button" className="btn btn-secondary" onClick={onCancel}>Cancelar</button><button type="submit" disabled={busy} className="btn btn-primary">{busy ? <LoaderCircle size={15} className="spin"/> : <Check size={15}/>} {submit}</button></div> }
function EmptyState({ icon: Icon, title, text, action }) { return <div className="empty-state"><div className="empty-icon"><Icon size={23}/></div><strong>{title}</strong><p>{text}</p>{action}</div> }

export default App
