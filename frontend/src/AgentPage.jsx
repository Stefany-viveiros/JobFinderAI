import { useState } from 'react'
import { Bot, Check, CircleHelp, ExternalLink, LoaderCircle, Play, Send, X } from 'lucide-react'

const ATTEMPT_LABEL = {
  prepared: 'Preparada', awaiting_approval: 'Aguardando aprovação', manual_required: 'Finalizar manualmente',
  sent: 'Enviada', failed: 'Falhou', cancelled: 'Cancelada',
}
const ATTEMPT_TONE = { prepared: 'blue', awaiting_approval: 'amber', manual_required: 'amber', sent: 'green', failed: 'red', cancelled: 'gray' }
const CHANNEL_LABEL = { email: 'E-mail automático', manual: 'Site da vaga (manual)', manual_confirmed: 'Confirmada manualmente' }
const MODE_LABEL = { api: 'API', html: 'Leitura de página', link_only: 'Somente link' }

export function AttemptPill({ status }) {
  return <span className={`status-pill ${ATTEMPT_TONE[status] || 'gray'}`}><i/>{ATTEMPT_LABEL[status] || status}</span>
}

export default function AgentPage({ settings, setSettings, onSave, onRun, runResult, attempts, sources, onApprove, onCancel, onConfirmManual, busy }) {
  const [filter, setFilter] = useState('todas')
  const [open, setOpen] = useState(null)
  const shown = attempts.filter(a => filter === 'todas' || a.status === filter)
  const set = (k, v) => setSettings(s => ({ ...s, [k]: v }))
  const noApproval = !settings.require_approval

  return <>
    <div className="section-heading"><div><div className="eyebrow">AGENTE DE CANDIDATURAS</div><h1>Agente</h1>
      <p>Busca, filtra estágio/júnior, avalia compatibilidade e prepara candidaturas. Nada é marcado como enviado sem envio real ou sua confirmação.</p></div>
      <div className="heading-actions"><button className="btn btn-primary" onClick={onRun} disabled={busy}>{busy ? <LoaderCircle size={16} className="spin"/> : <Play size={16}/>} Executar agente agora</button></div></div>

    {!settings.profile_ready && <div className="agent-alert"><CircleHelp size={16}/> Perfil incompleto: faltam {settings.profile_gaps?.join(', ')}. O agente coleta vagas, mas só prepara candidaturas com seus dados reais preenchidos em “Perfil profissional”.</div>}
    {!settings.email_ready && <div className="agent-alert"><CircleHelp size={16}/> Envio por e-mail indisponível: configure SMTP_HOST, SMTP_FROM, SMTP_USERNAME e SMTP_PASSWORD no <code>.env</code>. Sem isso, toda candidatura é preparada para finalização manual no site da vaga.</div>}
    {noApproval && settings.auto_apply_enabled && <div className="agent-alert warn"><CircleHelp size={16}/> Aprovação desativada com envio automático ligado: o agente enviará e-mails sem revisão, até o limite diário.</div>}

    <div className="panel agent-settings">
      <div className="panel-heading"><div><h2>Configurações</h2><p>Enviadas automaticamente hoje: <strong>{settings.sent_today ?? 0}</strong> de {settings.daily_limit}</p></div></div>
      <label className="check-row"><input type="checkbox" checked={!!settings.auto_apply_enabled} onChange={e => set('auto_apply_enabled', e.target.checked)}/> Envio automático habilitado (somente vagas com e-mail de candidatura publicado)</label>
      <label className="check-row"><input type="checkbox" checked={!!settings.require_approval} onChange={e => set('require_approval', e.target.checked)}/> Exigir minha aprovação antes de cada envio</label>
      <div className="form-grid">
        <label className="field"><span>Limite diário de envios automáticos</span><input type="number" min="0" max="50" value={settings.daily_limit ?? 5} onChange={e => set('daily_limit', Number(e.target.value))}/></label>
        <label className="field"><span>Compatibilidade mínima para preparar (%)</span><input type="number" min="0" max="100" value={settings.min_score ?? 60} onChange={e => set('min_score', Number(e.target.value))}/></label>
      </div>
      <div className="modal-actions"><button className="btn btn-secondary" onClick={onSave} disabled={busy}><Check size={15}/> Salvar configurações</button></div>
    </div>

    {runResult && <div className="panel agent-result"><div className="panel-heading"><div><h2>Última execução</h2><p>Resultado real da rodada</p></div></div>
      <div className="agent-result-grid">{[['Recebidas', runResult.received], ['Salvas', runResult.saved], ['Duplicadas', runResult.duplicates], ['Fora do perfil (nível/área)', runResult.filtered_out], ['Candidatas', runResult.candidates], ['Aguardando aprovação', runResult.awaiting_approval], ['Manuais', runResult.manual_required], ['Enviadas', runResult.sent], ['Falhas', runResult.failed], ['Limite diário', runResult.skipped_daily_limit]].map(([l, v]) => <div key={l}><strong>{v ?? 0}</strong><span>{l}</span></div>)}</div>
      {runResult.message && <p className="muted small">{runResult.message}</p>}
      {runResult.errors?.length > 0 && <ul className="agent-errors">{runResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}</div>}

    <div className="panel">
      <div className="panel-heading"><div><h2>Fila e histórico de candidaturas</h2><p>Revise o texto antes de aprovar</p></div>
        <select className="compact-select" value={filter} onChange={e => setFilter(e.target.value)}><option value="todas">Todas</option>{Object.entries(ATTEMPT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
      {shown.length ? <div className="attempt-list">{shown.map(a => {
        const belowMinimum = Number(a.job.compatibility || 0) < Number(settings.min_score ?? 60)
        const mandatoryUnconfirmed = (a.job.missing_reasons || '').includes('Requisito(s) obrigatório(s) não identificado(s)')
        return <article className="attempt-card" key={a.id}>
        <div className="attempt-head"><div><strong>{a.job.title}</strong><span>{a.job.company} · {a.job.source} · {a.job.compatibility}%</span></div><AttemptPill status={a.status}/></div>
        <div className="attempt-meta"><span>{CHANNEL_LABEL[a.channel] || a.channel}</span>{a.recipient && <span>Para: {a.recipient}</span>}<span>{a.updated_at ? new Date(a.updated_at + 'Z').toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : ''}</span></div>
        {a.detail && <p className="attempt-detail">{a.detail}</p>}
        {belowMinimum && <p className="attempt-detail">A compatibilidade atual ({a.job.compatibility}%) está abaixo do mínimo configurado ({settings.min_score ?? 60}%). Revise antes de continuar.</p>}
        {mandatoryUnconfirmed && <p className="attempt-detail">Há requisito(s) obrigatório(s) ainda não identificados no perfil. A aprovação por e-mail fica bloqueada até a revisão.</p>}
        {open === a.id && <pre className="attempt-message">{a.subject}{'\n\n'}{a.message}</pre>}
        <div className="attempt-actions">
          <button className="text-action" onClick={() => setOpen(open === a.id ? null : a.id)}>{open === a.id ? 'Ocultar texto' : 'Ver texto preparado'}</button>
          <a className="btn btn-secondary btn-sm" href={a.job.url} target="_blank" rel="noreferrer">Abrir vaga <ExternalLink size={13}/></a>
          {a.channel === 'email' && ['prepared', 'awaiting_approval', 'failed'].includes(a.status) && <button className="btn btn-primary btn-sm" disabled={busy || !settings.email_ready || belowMinimum || mandatoryUnconfirmed} onClick={() => onApprove(a.id)}><Send size={13}/> {a.status === 'failed' ? 'Tentar novamente' : 'Aprovar e enviar'}</button>}
          {['manual_required', 'prepared', 'awaiting_approval'].includes(a.status) && a.channel !== 'email' && <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => onConfirmManual(a.job.id)}><Check size={13}/> Já enviei no site</button>}
          {['prepared', 'awaiting_approval', 'manual_required', 'failed'].includes(a.status) && <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => onCancel(a.id)}><X size={13}/> Cancelar</button>}
        </div></article>
      })}</div>
        : <div className="empty-state"><div className="empty-icon"><Bot size={23}/></div><strong>Nenhuma candidatura nesta visão</strong><p>Execute o agente ou use “Preparar candidatura” em uma vaga.</p></div>}
    </div>

    <div className="panel">
      <div className="panel-heading"><div><h2>Fontes de vagas</h2><p>O que cada plataforma realmente permite</p></div></div>
      <div className="table-wrap"><table className="data-table"><thead><tr><th>Fonte</th><th>Coleta</th><th>Candidatura automática</th><th>Observação</th></tr></thead>
        <tbody>{(sources?.sources || []).map(s => <tr key={s.name}><td><strong>{s.name}</strong></td><td>{MODE_LABEL[s.mode]}</td><td>{s.apply_api ? 'Sim' : 'Não (site original)'}</td><td className="small">{s.note}</td></tr>)}</tbody></table></div>
      {sources?.external_links?.length > 0 && <div className="external-links"><strong>Buscar manualmente (Indeed e Vagas.com):</strong>
        {sources.external_links.map((l, i) => <a key={i} href={l.url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">{l.source}: {l.query} <ExternalLink size={12}/></a>)}
        <span className="muted small">Encontrou algo? Use “Adicionar manualmente” em Buscar vagas. Nenhuma página dessas plataformas é raspada.</span></div>}
    </div>
  </>
}
