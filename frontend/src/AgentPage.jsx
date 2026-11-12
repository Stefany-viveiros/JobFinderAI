import { useEffect, useState } from 'react'
import { Bot, Check, CircleHelp, ExternalLink, LoaderCircle, Play, Send, X } from 'lucide-react'

const ATTEMPT_LABEL = {
  prepared: 'Preparada', awaiting_approval: 'Aguardando aprovação', manual_required: 'Finalizar manualmente',
  sent: 'Enviada', failed: 'Falhou', cancelled: 'Cancelada',
}
const ATTEMPT_TONE = { prepared: 'blue', awaiting_approval: 'amber', manual_required: 'amber', sent: 'green', failed: 'red', cancelled: 'gray' }
const CHANNEL_LABEL = { email: 'E-mail automático', manual: 'Site da vaga (manual)', manual_confirmed: 'Confirmada manualmente' }
const MODE_LABEL = { api: 'API pública/feed', html: 'Leitura de página', link_only: 'Link externo' }
const COLLECTION_LABEL = { active: 'Coleta ativa', external: 'Atalho externo' }

export function AttemptPill({ status }) {
  return <span className={`status-pill ${ATTEMPT_TONE[status] || 'gray'}`}><i/>{ATTEMPT_LABEL[status] || status}</span>
}

export default function AgentPage({ settings, setSettings, onSave, onRun, runResult, attempts, sources, onApprove, onCancel, onConfirmManual, smtp, onSaveSmtp, onDeleteSmtp, busy }) {
  const [filter, setFilter] = useState('todas')
  const [open, setOpen] = useState(null)
  const [smtpPassword, setSmtpPassword] = useState('')
  const [smtpForm, setSmtpForm] = useState({ host: '', port: 587, username: '', from_email: '', use_tls: true })
  useEffect(() => {
    setSmtpForm({
      host: smtp?.host || '',
      port: smtp?.port || 587,
      username: smtp?.username || '',
      from_email: smtp?.from_email || '',
      use_tls: smtp?.use_tls ?? true,
    })
  }, [smtp])
  const updateSmtp = (key, value) => setSmtpForm(current => ({ ...current, [key]: value }))
  const shown = attempts.filter(a => filter === 'todas' || a.status === filter)
  const set = (k, v) => setSettings(s => ({ ...s, [k]: v }))
  const noApproval = !settings.require_approval

  return <>
    <div className="section-heading"><div><div className="eyebrow">AGENTE DE CANDIDATURAS</div><h1>Agente</h1>
      <p>Busca, filtra estágio/júnior, avalia compatibilidade e prepara candidaturas. Nada é marcado como enviado sem envio real ou sua confirmação.</p></div>
      <div className="heading-actions"><button className="btn btn-primary" onClick={onRun} disabled={busy}>{busy ? <LoaderCircle size={16} className="spin"/> : <Play size={16}/>} Executar agente agora</button></div></div>

    {!settings.profile_ready && <div className="agent-alert"><CircleHelp size={16}/> Perfil incompleto: faltam {settings.profile_gaps?.join(', ')}. O agente coleta vagas, mas só prepara candidaturas com seus dados reais preenchidos em “Perfil profissional”.</div>}
    {!settings.email_ready && <div className="agent-alert"><CircleHelp size={16}/> {settings.email_block_reason || 'Envio por e-mail indisponível: configure sua conexão SMTP individual abaixo. Sem isso, toda candidatura será preparada para finalização manual no site da vaga.'}</div>}
    {noApproval && settings.auto_apply_enabled && <div className="agent-alert warn"><CircleHelp size={16}/> Aprovação desativada com envio automático ligado: o agente enviará e-mails sem revisão, até o limite diário.</div>}

    <div className="panel agent-settings">
      <div className="panel-heading"><div><h2>Configurações</h2><p>Enviadas automaticamente hoje: <strong>{settings.sent_today ?? 0}</strong> de {settings.daily_limit}</p></div></div>
      <label className="check-row"><input type="checkbox" checked={!!settings.auto_apply_enabled} onChange={e => set('auto_apply_enabled', e.target.checked)}/> Envio automático habilitado (somente vagas com e-mail de candidatura publicado)</label>
      <label className="check-row"><input type="checkbox" checked={!!settings.require_approval} onChange={e => set('require_approval', e.target.checked)}/> Exigir minha aprovação antes de cada envio</label>
      <div className="form-grid">
        <label className="field"><span>Limite diário de envios automáticos</span><input type="number" min="0" max="50" value={settings.daily_limit ?? 5} onChange={e => set('daily_limit', Number(e.target.value))}/></label>
        <label className="field"><span>Compatibilidade mínima para preparar (%)</span><input type="number" min="0" max="100" value={settings.min_score ?? 80} onChange={e => set('min_score', Number(e.target.value))}/></label>
      </div>
      <div className="modal-actions"><button className="btn btn-secondary" onClick={onSave} disabled={busy}><Check size={15}/> Salvar configurações</button></div>
    </div>

    <section className="panel agent-settings">
      <div className="panel-heading"><div><h2>Conexão de e-mail individual</h2><p>{smtp?.configured ? (smtp.ready ? 'Sua conta SMTP está cadastrada. A senha nunca é exibida novamente.' : 'A conta está cadastrada, mas a chave de criptografia do servidor não está disponível.') : 'Conecte seu próprio provedor para habilitar recursos de e-mail.'}{settings.email_block_reason ? ' O envio de candidaturas permanece bloqueado até o currículo individual poder ser anexado com segurança.' : ''}</p></div><span className={smtp?.ready ? 'status-pill green' : 'status-pill gray'}><i/>{smtp?.ready ? 'SMTP conectado' : smtp?.configured ? 'Chave indisponível' : 'Não configurado'}</span></div>
      <div className="form-grid">
        <label className="field"><span>Servidor SMTP</span><input value={smtpForm.host || smtp?.host || ''} onChange={e => updateSmtp('host', e.target.value)} placeholder="smtp.gmail.com" autoComplete="off"/></label>
        <label className="field"><span>Porta</span><input type="number" min="1" max="65535" value={smtpForm.port} onChange={e => updateSmtp('port', Number(e.target.value))}/></label>
        <label className="field"><span>Usuário / e-mail de autenticação</span><input value={smtpForm.username || smtp?.username || ''} onChange={e => updateSmtp('username', e.target.value)} autoComplete="username"/></label>
        <label className="field"><span>Remetente</span><input type="email" value={smtpForm.from_email || smtp?.from_email || ''} onChange={e => updateSmtp('from_email', e.target.value)} placeholder="voce@exemplo.com"/></label>
        <label className="field"><span>Senha de app SMTP</span><input type="password" value={smtpPassword} onChange={e => setSmtpPassword(e.target.value)} placeholder={smtp?.configured ? 'Informe uma nova senha para atualizar' : 'Senha de app do provedor'} autoComplete="new-password"/></label>
      </div>
      <label className="check-row"><input type="checkbox" checked={smtpForm.use_tls} onChange={e => updateSmtp('use_tls', e.target.checked)}/> Usar conexão TLS</label>
      <div className="modal-actions"><button className="btn btn-primary" disabled={busy || !smtpPassword || !(smtpForm.host || smtp?.host) || !(smtpForm.username || smtp?.username) || !(smtpForm.from_email || smtp?.from_email)} onClick={async () => { const ok = await onSaveSmtp({ ...smtpForm, host: smtpForm.host || smtp?.host, username: smtpForm.username || smtp?.username, from_email: smtpForm.from_email || smtp?.from_email, password: smtpPassword }); if (ok) setSmtpPassword('') }}><Check size={15}/> Salvar conexão SMTP</button>{smtp?.configured && <button className="btn btn-secondary" disabled={busy} onClick={onDeleteSmtp}><X size={15}/> Remover conexão</button>}</div>
      <p className="muted small">A senha é cifrada antes de ser salva. Use uma senha de app do provedor, nunca sua senha principal. O envio só ocorre após sua aprovação quando essa opção estiver ativada.</p>
    </section>

    {runResult && <div className="panel agent-result"><div className="panel-heading"><div><h2>Última execução</h2><p>Resultado real da rodada</p></div></div>
      <div className="agent-result-grid">{[['Recebidas', runResult.received], ['Salvas', runResult.saved], ['Duplicadas', runResult.duplicates], ['Fora do perfil (nível/área)', runResult.filtered_out], ['Candidatas', runResult.candidates], ['Aguardando aprovação', runResult.awaiting_approval], ['Manuais', runResult.manual_required], ['Enviadas', runResult.sent], ['Falhas', runResult.failed], ['Limite diário', runResult.skipped_daily_limit]].map(([l, v]) => <div key={l}><strong>{v ?? 0}</strong><span>{l}</span></div>)}</div>
      {runResult.message && <p className="muted small">{runResult.message}</p>}
      {runResult.errors?.length > 0 && <ul className="agent-errors">{runResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}</div>}

    <div className="panel">
      <div className="panel-heading"><div><h2>Fila e histórico de candidaturas</h2><p>Revise o texto antes de aprovar</p></div>
        <select className="compact-select" value={filter} onChange={e => setFilter(e.target.value)}><option value="todas">Todas</option>{Object.entries(ATTEMPT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
      {shown.length ? <div className="attempt-list">{shown.map(a => {
        const belowMinimum = Number(a.job.compatibility || 0) < Number(settings.min_score ?? 80)
        const mandatoryUnconfirmed = (a.job.missing_reasons || '').includes('Requisito(s) obrigatório(s) não identificado(s)')
        return <article className="attempt-card" key={a.id}>
        <div className="attempt-head"><div><strong>{a.job.title}</strong><span>{a.job.company} · {a.job.source} · {a.job.compatibility}%</span></div><AttemptPill status={a.status}/></div>
        <div className="attempt-meta"><span>{CHANNEL_LABEL[a.channel] || a.channel}</span>{a.recipient && <span>Para: {a.recipient}</span>}<span>{a.updated_at ? new Date(a.updated_at + 'Z').toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : ''}</span></div>
        {a.detail && <p className="attempt-detail">{a.detail}</p>}
        {belowMinimum && <p className="attempt-detail">A compatibilidade atual ({a.job.compatibility}%) está abaixo do mínimo configurado ({settings.min_score ?? 80}%). Revise antes de continuar.</p>}
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
      <div className="table-wrap"><table className="data-table"><thead><tr><th>Fonte</th><th>Disponibilidade</th><th>Tipo de integração</th><th>Candidatura automática</th><th>Observação</th></tr></thead>
        <tbody>{(sources?.sources || []).map(s => <tr key={s.name}><td><strong>{s.name}</strong></td><td><span className={`status-pill ${s.search_api ? 'green' : 'gray'}`}><i/>{s.search_api ? COLLECTION_LABEL.active : COLLECTION_LABEL.external}</span></td><td>{MODE_LABEL[s.mode] || 'Não informado'}</td><td>{s.apply_api ? 'Disponível' : 'Não (site original)'}</td><td className="small">{s.note}</td></tr>)}</tbody></table></div>
      <p className="muted small">Coleta ativa significa que o JobFinder consegue importar anúncios dessa fonte. Isso não concede permissão para enviar candidaturas em nome da pessoa. O envio automático só é usado quando existe um canal compatível e configurado; nos demais casos, a candidatura é concluída no portal original.</p>
      {sources?.external_links?.length > 0 && <div className="external-links"><strong>Explorar outros portais de emprego:</strong>
        {sources.external_links.map((l, i) => <a key={i} href={l.url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">{l.source}: {l.query} <ExternalLink size={12}/></a>)}
        <span className="muted small">Encontrou algo? Use “Adicionar manualmente” em Buscar vagas. Esses atalhos não coletam vagas nem automatizam candidaturas; o agente só importa fontes com integração ativa.</span></div>}
    </div>
  </>
}
