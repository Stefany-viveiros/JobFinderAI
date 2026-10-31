import { useCallback, useEffect, useState } from 'react'
import {
  Activity, BarChart3, CalendarDays, CheckCircle2, Clock3, Database,
  Layers3, LoaderCircle, RefreshCw, Sparkles, TrendingUp, TriangleAlert,
  Target, BookOpen, Plus, Trash2,
} from 'lucide-react'

const API = 'http://127.0.0.1:8000/api'

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || body.message || `Erro ${response.status}`)
  return body
}

const number = (value) => new Intl.NumberFormat('pt-BR').format(value || 0)
const date = (value) => value ? new Date(value).toLocaleDateString('pt-BR') : 'Não informado'

export default function MarketIntelligencePage() {
  const [analysis, setAnalysis] = useState(null)
  const [combinations, setCombinations] = useState([])
  const [gap, setGap] = useState(null)
  const [plan, setPlan] = useState({ items: [], summary: {} })
  const [planLoading, setPlanLoading] = useState(true)
  const [addingSkill, setAddingSkill] = useState(null)
  const [updatingItem, setUpdatingItem] = useState(null)
  const [level, setLevel] = useState('both')
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadAnalysis = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const latest = await request('/market/analysis/latest')
      setAnalysis(latest.available ? latest : null)
      if (latest.available) {
        const [pairs, profileGap] = await Promise.all([
          request(`/market/combinations?run_id=${latest.run.id}&limit=8`),
          request(`/market/profile-gap?run_id=${latest.run.id}`),
        ])
        setCombinations(pairs.combinations || [])
        setGap(profileGap.available ? profileGap : null)
      } else {
        setCombinations([])
        setGap(null)
      }
    } catch (err) {
      setError(err.message || 'Não foi possível carregar a análise.')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadPlan = useCallback(async () => {
    setPlanLoading(true)
    try {
      const result = await request('/market/development-plan')
      setPlan(result)
    } catch (err) {
      setError(err.message || 'Não foi possível carregar seu plano de desenvolvimento.')
    } finally {
      setPlanLoading(false)
    }
  }, [])

  useEffect(() => { loadAnalysis(); loadPlan() }, [loadAnalysis, loadPlan])

  async function addToPlan(skill) {
    setAddingSkill(skill.skill_id)
    setError('')
    setMessage('')
    try {
      const result = await request('/market/development-plan', {
        method: 'POST',
        body: JSON.stringify({ skill_id: skill.skill_id, run_id: gap?.run_id, estimated_hours: 4 }),
      })
      setPlan(result.plan)
      setMessage(`${skill.name} foi adicionada ao seu plano de desenvolvimento.`)
    } catch (err) {
      setError(err.message || 'Não foi possível adicionar a competência ao plano.')
    } finally {
      setAddingSkill(null)
    }
  }

  async function updatePlanItem(itemId, changes) {
    setUpdatingItem(itemId)
    setError('')
    try {
      const result = await request(`/market/development-plan/${itemId}`, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      })
      setPlan(current => ({
        ...current,
        items: current.items.map(item => item.id === itemId ? result.item : item),
      }))
      await loadPlan()
    } catch (err) {
      setError(err.message || 'Não foi possível atualizar a meta.')
    } finally {
      setUpdatingItem(null)
    }
  }

  async function removePlanItem(itemId) {
    setUpdatingItem(itemId)
    try {
      await request(`/market/development-plan/${itemId}`, { method: 'DELETE' })
      await loadPlan()
      setMessage('Meta removida do plano.')
    } catch (err) {
      setError(err.message || 'Não foi possível remover a meta.')
    } finally {
      setUpdatingItem(null)
    }
  }

  async function runAnalysis() {
    setRunning(true)
    setError('')
    setMessage('')
    try {
      const result = await request('/market/analysis/run', {
        method: 'POST',
        body: JSON.stringify({ level_scope: level, days: Number(days) }),
      })
      const [latest, pairs, profileGap] = await Promise.all([
        request('/market/analysis/latest'),
        request(`/market/combinations?run_id=${result.run_id}&limit=8`),
        request(`/market/profile-gap?run_id=${result.run_id}`),
      ])
      setAnalysis(latest.available ? latest : null)
      setCombinations(pairs.combinations || [])
      setGap(profileGap.available ? profileGap : null)
      setMessage(`Análise concluída: ${number(result.total_jobs)} vagas analisadas e ${number(result.skills_detected)} competências identificadas.`)
    } catch (err) {
      setError(err.message || 'Não foi possível executar a análise.')
    } finally {
      setRunning(false)
    }
  }

  const run = analysis?.run
  const skills = analysis?.skills || []
  const maxRate = Math.max(1, ...skills.map(skill => skill.mention_rate || 0))

  return <>
    <div className="section-heading market-heading">
      <div>
        <div className="eyebrow">DADOS PARA DECISÕES DE CARREIRA</div>
        <h1>Inteligência de mercado</h1>
        <p>Descubra quais competências aparecem nas oportunidades de estágio e nível júnior em tecnologia.</p>
      </div>
      <button className="btn btn-primary" onClick={runAnalysis} disabled={running || loading}>
        {running ? <LoaderCircle size={16} className="spin"/> : <RefreshCw size={16}/>}
        {running ? 'Analisando vagas...' : 'Atualizar análise'}
      </button>
    </div>

    <section className="market-control-panel panel">
      <div className="market-control-copy">
        <div className="market-control-icon"><Activity size={19}/></div>
        <div><strong>Configurar análise</strong><span>Escolha o recorte das vagas já coletadas pelo JobFinder AI.</span></div>
      </div>
      <div className="market-filters">
        <label className="market-filter"><span>Nível da oportunidade</span>
          <select value={level} onChange={event => setLevel(event.target.value)}>
            <option value="both">Estágio e júnior</option>
            <option value="estagio">Somente estágio</option>
            <option value="junior">Somente júnior</option>
          </select>
        </label>
        <label className="market-filter"><span>Período de primeira coleta</span>
          <select value={days} onChange={event => setDays(event.target.value)}>
            <option value="30">Últimos 30 dias</option>
            <option value="60">Últimos 60 dias</option>
            <option value="90">Últimos 90 dias</option>
          </select>
        </label>
      </div>
    </section>

    {error && <div className="market-alert error"><TriangleAlert size={17}/><span>{error}. Confira se a API do JobFinder AI está disponível.</span></div>}
    {message && <div className="market-alert success"><CheckCircle2 size={17}/><span>{message}</span></div>}

    {loading ? <div className="panel market-empty"><LoaderCircle className="spin" size={24}/><span>Carregando indicadores...</span></div> :
      !analysis ? <section className="panel market-empty">
        <div className="market-empty-icon"><BarChart3 size={27}/></div>
        <h2>Sua primeira análise começa aqui</h2>
        <p>O JobFinder AI vai examinar as vagas de estágio e júnior já salvas, identificar competências e calcular a frequência de cada uma.</p>
        <button className="btn btn-primary" onClick={runAnalysis} disabled={running}>{running ? <LoaderCircle size={15} className="spin"/> : <Sparkles size={15}/>} Gerar primeira análise</button>
      </section> : <>
        <div className="market-snapshot-meta">
          <span><CalendarDays size={14}/> Janela: {date(run.period_start)} a {date(run.period_end)}</span>
          <span><Clock3 size={14}/> Atualizada em {date(run.created_at)}</span>
          <span><Database size={14}/> Fontes: {(run.sources || []).join(', ') || 'Não identificadas'}</span>
        </div>

        <div className="market-metric-grid">
          <article className="market-metric"><div className="market-metric-icon purple"><Database size={18}/></div><span>Vagas analisadas</span><strong>{number(run.total_jobs)}</strong><small>Vagas distintas no recorte</small></article>
          <article className="market-metric"><div className="market-metric-icon blue"><Layers3 size={18}/></div><span>Competências encontradas</span><strong>{number(skills.length)}</strong><small>Termos agrupados por sinônimos</small></article>
          <article className="market-metric"><div className="market-metric-icon green"><CheckCircle2 size={18}/></div><span>Descrições aproveitáveis</span><strong>{number(run.jobs_with_description)}</strong><small>Com pelo menos 80 caracteres</small></article>
          <article className="market-metric"><div className="market-metric-icon amber"><TrendingUp size={18}/></div><span>Combinações recorrentes</span><strong>{number(combinations.length)}</strong><small>Pares de competências identificados</small></article>
        </div>

        {run.quality_notes && <div className="market-alert warning"><TriangleAlert size={17}/><span>{run.quality_notes}</span></div>}
        {run.total_jobs < 30 && <div className="market-sample-note">A amostra ainda é pequena. Os resultados abaixo são observações das vagas coletadas, não um ranking representativo de todo o mercado.</div>}

        <div className="market-content-grid">
          <section className="panel market-panel">
            <div className="panel-heading"><div><h2>Competências mais mencionadas</h2><p>Percentual de vagas do recorte que citam cada competência.</p></div><span className="market-count">{skills.length} competências</span></div>
            {skills.length ? <div className="market-skill-list">{skills.slice(0, 15).map(skill =>
              <div className="market-skill-row" key={skill.skill_id}>
                <div className="market-skill-top"><div><strong>{skill.name}</strong><span>{skill.category}</span></div><div className="market-skill-value"><strong>{skill.mention_rate.toLocaleString('pt-BR')}%</strong><small>{number(skill.jobs_count)} vagas</small></div></div>
                <div className="market-bar"><i style={{ width: `${Math.min(100, (skill.mention_rate / maxRate) * 100)}%` }}/></div>
              </div>
            )}</div> : <div className="market-inline-empty">Nenhuma competência foi identificada no texto das vagas deste período.</div>}
            <p className="market-footnote">Uma vaga pode mencionar várias competências. Por isso, os percentuais não precisam somar 100%.</p>
          </section>

          <section className="panel market-panel">
            <div className="panel-heading"><div><h2>Combinações de tecnologias</h2><p>Competências encontradas juntas na mesma vaga.</p></div><span className="market-count">Coocorrência</span></div>
            {combinations.length ? <div className="market-pair-list">{combinations.map((pair, index) =>
              <div className="market-pair-row" key={`${pair.skill_a}-${pair.skill_b}`}>
                <div className="market-pair-rank">{String(index + 1).padStart(2, '0')}</div>
                <div className="market-pair-names"><strong>{pair.skill_a}</strong><span>+</span><strong>{pair.skill_b}</strong><small>{number(pair.jobs_count)} vagas com as duas competências</small></div>
                <b>{pair.mention_rate.toLocaleString('pt-BR')}%</b>
              </div>
            )}</div> : <div className="market-inline-empty">Ainda não há combinações suficientes para exibir.</div>}
            <div className="market-pair-tip"><Sparkles size={16}/><span>Essas combinações ajudam a entender quais tecnologias costumam ser exigidas em conjunto.</span></div>
          </section>
        </div>

        <section className="panel market-panel market-gap-panel">
          <div className="panel-heading">
            <div><h2>Skill Gap: mercado × seu perfil</h2><p>O que as vagas pedem e quais evidências já aparecem no seu perfil profissional.</p></div>
            <span className="market-count">{gap ? `${gap.total_skills} competências` : 'Perfil não analisado'}</span>
          </div>
          {!gap ? <div className="market-inline-empty">Cadastre ou complete seu perfil profissional para comparar as competências com o mercado.</div> : <>
            <div className="market-gap-summary">
              <div><strong>{gap.counts?.experiencia || 0}</strong><span>Experiência</span></div>
              <div><strong>{(gap.counts?.projeto || 0) + (gap.counts?.praticada || 0)}</strong><span>Projetos e prática</span></div>
              <div><strong>{(gap.counts?.curso_concluido || 0) + (gap.counts?.certificacao || 0) + (gap.counts?.formacao || 0) + (gap.counts?.em_estudo || 0)}</strong><span>Formação e estudo</span></div>
              <div><strong>{gap.counts?.nao_identificada || 0}</strong><span>Não identificadas</span></div>
            </div>
            <div className="market-gap-list">{gap.items.slice(0, 20).map(item =>
              <article className="market-gap-item" key={item.skill_id}>
                <div className="market-gap-main">
                  <div><strong>{item.name}</strong><span>{item.category}</span></div>
                  <small>{item.jobs_count} vagas · {item.mention_rate.toLocaleString('pt-BR')}% de menção</small>
                </div>
                <div className="market-gap-status">
                  <span className={`market-status-pill status-${item.status}`}>{item.status_label}</span>
                  <small>{item.recommendation}</small>
                  <button className="market-add-goal" onClick={() => addToPlan(item)} disabled={addingSkill === item.skill_id || plan.items.some(goal => goal.skill_id === item.skill_id && goal.status !== 'completed')}>
                    {addingSkill === item.skill_id ? <LoaderCircle size={13} className="spin"/> : <Plus size={13}/>}
                    {plan.items.some(goal => goal.skill_id === item.skill_id && goal.status !== 'completed') ? 'Já no plano' : 'Adicionar ao plano'}
                  </button>
                </div>
              </article>
            )}</div>
            <p className="market-footnote">{gap.notice}</p>
          </>}
        </section>

        <section className="panel market-panel market-development-panel">
          <div className="panel-heading">
            <div><h2>Meu plano de desenvolvimento</h2><p>Transforme competências relevantes em atividades práticas e acompanhe seu progresso.</p></div>
            <span className="market-count">{plan.summary?.completion_rate || 0}% concluído</span>
          </div>
          <div className="market-plan-summary">
            <div><strong>{plan.summary?.total || 0}</strong><span>Metas</span></div>
            <div><strong>{plan.summary?.in_progress || 0}</strong><span>Em andamento</span></div>
            <div><strong>{plan.summary?.completed || 0}</strong><span>Concluídas</span></div>
            <div><strong>{number(plan.summary?.estimated_hours || 0)}h</strong><span>Horas estimadas</span></div>
          </div>
          {planLoading ? <div className="market-inline-empty"><LoaderCircle size={16} className="spin"/> Carregando plano...</div> :
            !plan.items?.length ? <div className="market-plan-empty"><Target size={23}/><strong>Seu plano começa com uma meta.</strong><span>Escolha uma competência no Skill Gap e adicione uma atividade prática.</span></div> :
            <div className="market-plan-list">{plan.items.map(item =>
              <article className={`market-plan-item ${item.status === 'completed' ? 'is-completed' : ''}`} key={item.id}>
                <div className="market-plan-item-head">
                  <div className="market-plan-title"><div className="market-plan-icon"><BookOpen size={16}/></div><div><strong>{item.title}</strong><span>{item.skill_name} · {item.estimated_hours}h estimadas</span></div></div>
                  <button className="market-plan-delete" title="Remover meta" onClick={() => removePlanItem(item.id)} disabled={updatingItem === item.id}><Trash2 size={15}/></button>
                </div>
                <p>{item.objective}</p>
                <div className="market-plan-activity"><strong>Atividade sugerida</strong><span>{item.activity}</span></div>
                <div className="market-plan-controls">
                  <label><span>Status</span><select value={item.status} disabled={updatingItem === item.id} onChange={event => updatePlanItem(item.id, { status: event.target.value })}>
                    <option value="planned">Planejada</option><option value="in_progress">Em andamento</option><option value="paused">Pausada</option><option value="completed">Concluída</option>
                  </select></label>
                  <label><span>Progresso</span><select value={item.progress_percent} disabled={updatingItem === item.id || item.status === 'completed'} onChange={event => updatePlanItem(item.id, { progress_percent: Number(event.target.value), status: Number(event.target.value) > 0 ? 'in_progress' : 'planned' })}>
                    <option value="0">0%</option><option value="25">25%</option><option value="50">50%</option><option value="75">75%</option><option value="99">Quase concluída</option>
                  </select></label>
                  <div className="market-plan-progress"><i style={{width: `${item.progress_percent}%`}}/></div>
                </div>
                <label className="market-plan-notes"><span>Suas anotações</span><textarea defaultValue={item.notes || ''} placeholder="Registre aprendizados, dificuldades ou links do seu projeto..." onBlur={event => { if(event.target.value !== (item.notes || '')) updatePlanItem(item.id, { notes: event.target.value }) }}/></label>
              </article>
            )}</div>
          }
        </section>

        <section className="market-disclaimer"><Database size={16}/><p>Os indicadores refletem somente as vagas armazenadas no seu JobFinder AI, dentro do período selecionado. A data considerada é a primeira coleta local, não necessariamente a publicação original. Competência não identificada no texto não significa que a empresa não a exija.</p></section>
      </>}
  </>
}
