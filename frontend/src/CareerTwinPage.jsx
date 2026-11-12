import { useCallback, useEffect, useState } from 'react'
import {
  Activity, AlertCircle, ArrowUpRight, BookOpen, BriefcaseBusiness, CheckCircle2,
  CircleHelp, Code2, GraduationCap, Layers3, LoaderCircle, RefreshCw, ShieldCheck,
  Sparkles, Target, UserRound,
} from 'lucide-react'

const API = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
let csrfToken = ''
const SOURCE_LABELS = {
  professional_experience: 'Experiência profissional',
  completed_project: 'Projeto concluído',
  ongoing_project: 'Projeto em andamento',
  completed_course: 'Curso concluído',
  ongoing_course: 'Curso em andamento',
  course_status_unspecified: 'Curso (situação não informada)',
  certification_record: 'Certificação cadastrada',
  education_record: 'Formação acadêmica',
  legacy_experience: 'Experiência (campo antigo)',
  legacy_project: 'Projeto (campo antigo)',
  legacy_certification: 'Certificação (campo antigo)',
  self_declared: 'Declarada no perfil',
  self_assessment: 'Autoavaliação de desafio',
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const response = await fetch(`${API}${path}`, {
    ...options, credentials: 'include', headers,
  })
  const returnedCsrf = response.headers.get('X-CSRF-Token')
  if (returnedCsrf) csrfToken = returnedCsrf
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || body.message || `Erro ${response.status}`)
  return body
}

function Metric({ icon: Icon, label, value, detail }) {
  return <article className="career-metric">
    <span className="career-metric-icon"><Icon size={18}/></span>
    <span className="career-metric-label">{label}</span>
    <strong>{value}</strong>
    <small>{detail}</small>
  </article>
}

function Evidence({ item }) {
  return <div className="career-evidence">
    <span className="career-evidence-dot"/>
    <div>
      <strong>{SOURCE_LABELS[item.source_type] || item.source_type}</strong>
      <span>{item.source_label}</span>
      {item.excerpt && <p>“{item.excerpt}”</p>}
    </div>
  </div>
}

export default function CareerTwinPage({ focusSection = null } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [ledger, setLedger] = useState([])
  const [reviewingId, setReviewingId] = useState(null)
  const [reviewHistory, setReviewHistory] = useState({})
  const [historyLoadingId, setHistoryLoadingId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const session = await request('/auth/me')
      csrfToken = session.csrf_token || csrfToken
      const [twin, evidence] = await Promise.all([
        request('/career-twin'),
        request('/career-evidence?limit=500'),
      ])
      setData(twin)
      setLedger(evidence.items || [])
    } catch (err) {
      setError(err.message || 'Não foi possível carregar seu Career Twin.')
    } finally {
      setLoading(false)
    }
  }, [])

  const reviewEvidence = async (item, decision) => {
    setReviewingId(item.id)
    setError('')
    try {
      await request(`/career-evidence/${item.id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          note: decision === 'confirmed'
            ? 'A pessoa confirmou que a informação corresponde à origem exibida.'
            : 'A pessoa marcou a menção como não relevante para sua trajetória.',
        }),
      })
      await load()
    } catch (err) {
      setError(err.message || 'Não foi possível registrar a revisão.')
    } finally {
      setReviewingId(null)
    }
  }

  const toggleReviewHistory = async (item) => {
    if (reviewHistory[item.id]) {
      setReviewHistory(current => ({ ...current, [item.id]: null }))
      return
    }
    setHistoryLoadingId(item.id)
    setError('')
    try {
      const result = await request(`/career-evidence/${item.id}/reviews`)
      setReviewHistory(current => ({ ...current, [item.id]: result.items || [] }))
    } catch (err) {
      setError(err.message || 'Não foi possível carregar o histórico de revisão.')
    } finally {
      setHistoryLoadingId(null)
    }
  }

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!focusSection || loading || !data?.available) return
    const targetIds = {
      skills: 'career-competencies',
      timeline: 'career-timeline',
    }
    document.getElementById(targetIds[focusSection] || 'career-competencies')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [focusSection, loading, data])

  if (loading) return <div className="career-loading"><LoaderCircle className="spin" size={24}/><span>Construindo sua visão profissional...</span></div>
  if (error) return <section className="panel career-state"><AlertCircle size={25}/><h2>Não foi possível carregar o Career Twin</h2><p>{error}</p><button className="btn btn-primary" onClick={load}><RefreshCw size={15}/> Tentar novamente</button></section>
  if (!data?.available) return <section className="panel career-state"><UserRound size={25}/><h2>Seu Career Twin começa pelo perfil</h2><p>{data?.message || 'Preencha seu perfil profissional para reunir suas competências e evidências.'}</p></section>

  const profile = data.profile || {}
  const summary = data.summary || {}
  const skills = data.skills || []
  const timeline = data.timeline || []
  const visibleSkills = skills.filter(item => filter === 'all' || (
    filter === 'evidence' ? item.evidence?.length > 0 :
    filter === 'declared' ? item.status === 'self_declared' :
    filter === 'market' ? Boolean(item.market) && !item.evidence?.length :
    item.status === 'not_found'
  ))

  return <div className="career-twin-page">
    <div className="career-hero">
      <div className="career-hero-copy">
        <span className="career-eyebrow"><Sparkles size={14}/> INTELIGÊNCIA DE CARREIRA</span>
        <h1>Seu Career Twin</h1>
        <p>Uma visão viva da sua trajetória, competências e evidências profissionais — com transparência sobre a origem de cada informação.</p>
        <div className="career-hero-person"><span className="career-avatar">{(profile.name || 'JF').trim().split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase()}</span><div><strong>{profile.name || 'Seu perfil profissional'}</strong><span>{[profile.course, profile.institution].filter(Boolean).join(' · ') || profile.interests || 'Objetivos profissionais não informados'}</span></div></div>
      </div>
      <div className="career-hero-symbol"><Layers3 size={48}/><span>CAREER<br/>INTELLIGENCE</span></div>
    </div>

    <div className="career-metrics-grid">
      <Metric icon={Layers3} label="Seções preenchidas" value={`${summary.completed_sections || 0}/${summary.total_sections || 0}`} detail="Visão geral do perfil"/>
      <Metric icon={ShieldCheck} label="Competências identificadas" value={summary.skills_identified || 0} detail="Encontradas nos registros"/>
      <Metric icon={CheckCircle2} label="Com evidências" value={summary.skills_with_evidence || 0} detail="Com origem rastreável"/>
      <Metric icon={Target} label="Autoavaliações" value={summary.skills_with_self_assessment || 0} detail="Não equivalem a certificação"/>
    </div>

    <section className="panel career-panel" id="career-evidence-ledger">
      <div className="career-panel-heading">
        <div>
          <span className="career-eyebrow">HISTÓRICO RASTREÁVEL</span>
          <h2>Ledger de evidências</h2>
          <p>{ledger.length} registro(s) · {ledger.filter(item => item.is_active).length} ativo(s). Alterações preservam versões anteriores.</p>
        </div>
        <span className="career-status has-evidence">Histórico persistente</span>
      </div>
      {ledger.length ? <div className="career-evidence-list">
        {ledger.map(item => <div className={item.is_active ? 'career-evidence' : 'career-evidence career-evidence-superseded'} key={item.id}>
          <span className="career-evidence-dot"/>
          <div>
            <strong>{item.skill_name} · {SOURCE_LABELS[item.source_type] || item.source_type}</strong>
            <span>{item.source_label}</span>
            {item.excerpt && <p>“{item.excerpt}”</p>}
            <small>{item.is_active ? 'Versão atual' : 'Versão anterior'} · {item.verification_label}</small>
            <small>
              {item.review_decision === 'confirmed' ? 'Revisada: origem confirmada pela pessoa' :
                item.review_decision === 'dismissed' ? 'Revisada: marcada como não relevante' :
                'Aguardando revisão humana'}
              {item.reviewed_at ? ` · ${new Date(item.reviewed_at).toLocaleDateString('pt-BR')}` : ''}
            </small>
            {item.is_active && <div className="career-evidence-review-actions">
              <button className="btn btn-secondary btn-sm" disabled={reviewingId === item.id || item.review_decision === 'confirmed'} onClick={() => reviewEvidence(item, 'confirmed')}>
                {reviewingId === item.id ? 'Salvando…' : 'Confirmar origem'}
              </button>
              <button className="btn btn-secondary btn-sm" disabled={reviewingId === item.id || item.review_decision === 'dismissed'} onClick={() => reviewEvidence(item, 'dismissed')}>
                Marcar não relevante
              </button>
            </div>}
            <div className="career-evidence-review-actions">
              <button className="btn btn-secondary btn-sm" disabled={historyLoadingId === item.id} onClick={() => toggleReviewHistory(item)}>
                {historyLoadingId === item.id ? 'Carregando…' : reviewHistory[item.id] ? 'Ocultar histórico' : 'Ver histórico'}
              </button>
            </div>
            {Array.isArray(reviewHistory[item.id]) && <ol className="career-review-history">
              {reviewHistory[item.id].length ? reviewHistory[item.id].map(review => <li key={review.id}>
                <strong>{review.decision === 'confirmed' ? 'Origem confirmada' : 'Marcada como não relevante'}</strong>
                <span>{review.note || 'Sem observação adicional'}</span>
                <small>{review.created_at ? new Date(review.created_at).toLocaleString('pt-BR') : 'Data não informada'}</small>
              </li>) : <li>Esta evidência ainda não possui revisões.</li>}
            </ol>}
          </div>
        </div>)}
      </div> : <div className="career-empty"><CircleHelp size={18}/><span>As evidências aparecerão aqui quando você salvar competências em experiências, projetos, cursos, formação ou autoavaliações.</span></div>}
      <p className="career-market-note">A revisão confirma apenas se a menção corresponde à origem exibida. Ela não comprova proficiência nem substitui avaliação técnica. Cada decisão é registrada no histórico, sem alterar a evidência original.</p>
    </section>

    <section className="panel career-panel" id="career-competencies">
      <div className="career-panel-heading"><div><span className="career-eyebrow">MAPA DE COMPETÊNCIAS</span><h2>O que seu histórico demonstra</h2><p>As categorias indicam onde a competência foi mencionada, não o seu nível de domínio.</p></div><button className="btn btn-secondary btn-sm" onClick={load}><RefreshCw size={14}/> Atualizar</button></div>
      <div className="career-filter-row">
        {[['all','Todas'],['evidence','Com evidências'],['declared','Declaradas'],['market','Demanda sem evidência'],['missing','Não identificadas']].map(([value,label]) => <button key={value} className={filter === value ? 'career-filter active' : 'career-filter'} onClick={() => setFilter(value)}>{label}</button>)}
      </div>
      {visibleSkills.length ? <div className="career-skill-grid">
        {visibleSkills.map(skill => <article className="career-skill-card" key={skill.name}>
          <div className="career-skill-heading"><div><strong>{skill.name}</strong><span>{skill.category || 'Competência'}</span></div><span className={skill.evidence?.length ? 'career-status has-evidence' : 'career-status'}>{skill.status_label}</span></div>
          {skill.market && <div className="career-market-context"><span>Presença no recorte de vagas</span><strong>{skill.market.mention_rate}%</strong><small>{skill.market.jobs_count} vagas analisadas · snapshot #{skill.market.run_id}</small></div>}
          {skill.evidence?.length ? <div className="career-evidence-list">{skill.evidence.map((item,index) => <Evidence key={`${skill.name}-${item.source_type}-${item.source_id ?? index}`} item={item}/>)}</div> : <p className="career-no-evidence">{skill.status === 'not_found' ? 'Não encontramos menção nos registros disponíveis. Isso não significa que você não tenha essa competência.' : 'Nenhuma evidência de perfil foi identificada.'}</p>}
          {skill.self_assessment && <div className="career-assessment"><div><strong>Autoavaliação registrada</strong><span>{skill.self_assessment.title}</span>{skill.self_assessment.plan_item_id && <small>Vinculada à meta #{skill.self_assessment.plan_item_id}</small>}</div>{skill.self_assessment.score != null && <b>{skill.self_assessment.score}/100</b>}<small>{skill.self_assessment.notice}</small>{skill.self_assessment.evidence_url && <a href={skill.self_assessment.evidence_url} target="_blank" rel="noreferrer">Ver evidência <ArrowUpRight size={13}/></a>}</div>}
        </article>)}
      </div> : <div className="career-empty"><CircleHelp size={20}/><span>Nenhuma competência corresponde a este filtro.</span></div>}
    </section>

    <div className="career-bottom-grid" id="career-timeline">
      <section className="panel career-panel">
        <div className="career-panel-heading"><div><span className="career-eyebrow">TRAJETÓRIA</span><h2>Seus registros profissionais</h2></div></div>
        <div className="career-record-list">
          <div><GraduationCap size={18}/><span><strong>Formação acadêmica</strong><small>{profile.educations?.length || 0} registro(s)</small></span></div>
          <div><BriefcaseBusiness size={18}/><span><strong>Experiências</strong><small>{profile.experiences?.length || 0} registro(s)</small></span></div>
          <div><Code2 size={18}/><span><strong>Projetos</strong><small>{profile.projects?.length || 0} registro(s)</small></span></div>
          <div><BookOpen size={18}/><span><strong>Cursos e certificações</strong><small>{(profile.courses?.length || 0) + (profile.certifications?.length || 0)} registro(s)</small></span></div>
        </div>
        <div className="career-timeline-heading"><strong>Histórico de evolução</strong><span>{timeline.length} evento(s)</span></div>
        {timeline.length ? <ol className="career-timeline">{timeline.map((event,index) => <li key={`${event.source_type}-${event.source_id ?? index}-${event.event_type}`}>
          <span className="career-timeline-marker"/>
          <div className="career-timeline-content">
            <div><strong>{event.title}</strong><span>{event.date ? new Date(event.date).toLocaleDateString('pt-BR') : 'Data não informada'}</span></div>
            <p>{event.detail}</p>
            <small>{({
              education_record: 'Formação acadêmica',
              professional_experience: 'Experiência profissional',
              completed_project: 'Projeto concluído',
              ongoing_project: 'Projeto em andamento',
              completed_course: 'Curso concluído',
              ongoing_course: 'Curso em andamento',
              certification_record: 'Certificação cadastrada',
              development_goal_created: 'Plano de desenvolvimento',
              development_goal_completed: 'Meta concluída',
              challenge_started: 'Desafio prático',
              self_assessment_submitted: 'Autoavaliação',
            })[event.event_type] || event.event_type}</small>
            {event.evidence_url && <a href={event.evidence_url} target="_blank" rel="noreferrer">Abrir evidência <ArrowUpRight size={12}/></a>}
          </div>
        </li>)}</ol> : <div className="career-empty"><CircleHelp size={18}/><span>Seu histórico aparecerá aqui conforme você cadastrar experiências, cursos, projetos e atividades de desenvolvimento.</span></div>}
      </section>
      <section className="panel career-panel">
        <div className="career-panel-heading"><div><span className="career-eyebrow">CONTEXTO DE MERCADO</span><h2>Demanda observada</h2></div></div>
        {data.market ? <><div className="career-market-date"><Activity size={16}/><span>Snapshot #{data.market.run_id} · {data.market.valid_jobs} vagas válidas</span></div><p className="career-market-note">As taxas de demanda são referências do recorte analisado, não previsões de contratação. Use-as junto às evidências do seu perfil.</p>{data.market.quality_notes && <small className="career-muted">{data.market.quality_notes}</small>}</> : <div className="career-no-market"><Target size={20}/><p>O perfil está disponível. Gere uma análise na área Inteligência de mercado para comparar suas competências com as exigências observadas nas vagas.</p></div>}
      </section>
    </div>

    <div className="career-disclaimer"><ShieldCheck size={17}/><p><strong>Transparência e limites.</strong> A extração é determinística e baseada na taxonomia do JobFinder. Menções textuais, projetos, cursos e autoavaliações não comprovam sozinhos proficiência. A ausência de uma competência no perfil não significa que você não a conheça.</p></div>
  </div>
}
