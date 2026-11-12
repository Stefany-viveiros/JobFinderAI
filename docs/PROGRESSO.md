# Progresso — JobFinder AI Proof-to-Opportunity Engine

**Branch:** `feature/proof-to-opportunity-engine`  
**Último commit:** `e15e0c250d37a19b561815c1560c331011bac438`  
**Atualização:** 12/11/2026.

## Estado de execução

| Fase | Estado | Evidência / pendência |
|---|---|---|
| A — Auditoria | Concluída | Matriz em `docs/AUDITORIA.md`; frontend, API, modelos, serviços, migrações, testes e deploy revisados na branch |
| B — Segurança e privacidade | Incrementos concluídos; liberação SaaS pendente | Consentimento explícito para Gemini, upload endurecido, rate limit, CSRF e testes de isolamento; gate continua fechado |
| C — Career Twin | Incremento concluído | Read model determinístico, evidências por origem, linha do tempo com dados da conta e eventos de plano/desafio; CI aprovado |
| D — Diagnóstico de oportunidades | Incremento concluído | Endpoint por vaga com classificação de requisitos e rastreabilidade de evidências; não mede proficiência; CI aprovado |
| E — Desenvolvimento e desafios | Parcial | Plano e autoavaliação existentes; conclusão aparece na linha do tempo, mas não existe ledger de eventos nem runner seguro |
| F — Candidaturas e agente | Incremento de histórico concluído; métricas parciais | Pipeline preservado; histórico por evento/conta no backend e frontend; migração aditiva e isolamento testado; métricas de conversão e cobertura das fontes pendentes |
| G — Inteligência de mercado | Incremento concluído | Snapshot, Skill Gap com contexto de amostra e comparação de dois snapshots equivalentes; agendamento recorrente ainda depende de infraestrutura |
| H — Qualidade e entrega | Parcial | CI SQLite/PostgreSQL/build aprovado; upload DOCX endurecido; downgrade de histórico preserva dados; não houve deploy; gates continuam fechados |

## Implementações commitadas nesta branch

- `73c9255` / `05ae7fb`: consentimento por importação antes de envio do currículo ao Gemini; extração local por padrão; rate limit e validação básica de arquivo.
- `cc26e06`: documentação inicial de auditoria e atualização do estado.
- `1ca1a6e`: testes de IDOR em aprovar/cancelar candidatura, gate fail-closed e CSRF.
- `f3d410a` / `cce41b5`: diagnóstico por requisito da vaga; correção do parser de frases.
- `a6dc733` / `a49e1dc`: metadados de amostra do Skill Gap e autenticação/CSRF no cliente da página de mercado; build corrigido.
- `d9c2a9f`: linha do tempo de Career Twin, metas concluídas e autoavaliações.
- `56c067e`: tendências entre snapshots comparáveis.
- `c5c00a0`: limites de expansão de DOCX antes da leitura.
- `9bd6a19`: bloqueio também no runner de lembretes SMTP globais.
- `145655c`: histórico de mudanças de etapa de candidatura e migração Alembic aditiva.
- `e15e0c2`: downgrade da migração de histórico não apaga eventos existentes.

## Evidências reais do GitHub Actions

| Commit | SQLite | PostgreSQL 16 | Vite |
|---|---:|---:|---|
| `05ae7fb` | 101 passaram, 1 ignorado | 102 passaram | Aprovado |
| `1ca1a6e` | 104 passaram, 1 ignorado | 105 passaram | Aprovado |
| `cce41b5` | 108 passaram, 1 ignorado | 109 passaram | Aprovado |
| `a49e1dc` | 109 passaram, 1 ignorado | 110 passaram | Aprovado |
| `d9c2a9f` | 109 passaram, 1 ignorado | 110 passaram | Aprovado |
| `56c067e` | 111 passaram, 1 ignorado | 112 passaram | Aprovado |

- Upload/consentimento: [CI 43140897026](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43140897026).
- Isolamento/CSRF: [CI 43141623537](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43141623537).
- Diagnóstico por vaga e amostra do Skill Gap: [CI 43143439053](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43143439053).
- Linha do tempo do Career Twin: [CI 43144640122](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43144640122).
- Tendências de mercado: [CI 43145152234](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43145152234).
- DOCX e limites ZIP: [CI 43146427900](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43146427900).
- Bloqueio do lembrete global: [CI 43146092761](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43146092761).
- Histórico de candidaturas: [CI 43147354689](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43147354689).

Os avisos de depreciação registrados pelo CI não foram tratados como falhas. Algumas execuções intermediárias falharam e foram corrigidas antes dos commits validados; não se alteraram testes para mascarar as falhas.

## Decisões de segurança e produto

1. Não alterar `main`, não executar deploy e não acessar banco de produção.
2. Manter `MULTITENANT_READY=false` até concluir a revisão endpoint a endpoint e validar o schema do banco de destino.
3. Manter `DEMO_READ_ONLY=true` no Render de demonstração.
4. Não atribuir dados legados sem proprietário automaticamente a uma conta.
5. Currículos só são enviados ao Gemini quando a pessoa autoriza explicitamente cada importação.
6. Ausência de menção significa “não identificada no registro”, nunca ausência de competência.
7. Evidências textuais, projetos, cursos e certificações não comprovam sozinhos proficiência.
8. Desafios continuam autoavaliação; não existe execução de código de usuário.
9. Tendências só com snapshots de mesmo nível, janela, taxonomia e extrator; são observações da amostra local, não previsões.
10. A coleta usa a data da primeira observação local, não um histórico completo da data original de publicação de cada vaga.

## Pendências reais

- Concluir revisão endpoint a endpoint e de IDOR para todas as rotas privadas, com foco em operações de conta e configurações.
- Validar upgrades/rollbacks Alembic em cópia controlada de banco e revisar os registros sem `user_id`.
- Definir agendador recorrente real para snapshots de mercado (por exemplo, job/cron compatível com infraestrutura contratada); não há execução quinzenal automática ativa.
- Completar análise de candidaturas com métricas de conversão sem inferir resultados inexistentes.
- Evoluir registro versionado de evidências (ledger), sem duplicar o perfil.
- Não implementar runner de código até existir isolamento descartável, sem rede e com limites testados.
- Revisar configuração de e-mail por usuário; o destinatário SMTP global não deve ser liberado no SaaS.
- Atualizar e validar a configuração de produção somente após aprovação de segurança.

## Próximo passo exato

Auditar todas as rotas restantes de autenticação, perfil, configurações e candidaturas e acrescentar testes de acesso cruzado onde ainda faltar cobertura. Depois revisar o schema/migrações em ambiente de teste PostgreSQL e só então decidir sobre qualquer mudança de `MULTITENANT_READY`.  


## Incrementos recentes de segurança e candidaturas — 12/11/2026

- `jobfinder/resume_parser.py`: limita entradas ZIP, tamanho descompactado por entrada e total, valida componentes DOCX e recusa taxa de compressão excessiva. O upload continua limitado a 5 MB.
- `jobfinder/mailer.py`: bloqueia o lembrete global também quando o runner é chamado diretamente em modo multiusuário.
- `ApplicationEvent`: registra a sequência de status e a origem (SMTP, confirmação manual ou atualização manual) com `user_id`.
- `GET /api/applications/{application_id}/history`: confirma que a candidatura pertence à conta e retorna somente eventos da mesma conta.
- `frontend/src/App.jsx`: painel de candidaturas permite abrir histórico, com estados de carregamento, erro e vazio.
- `20261112_0002`: migração aditiva. O downgrade interrompe se houver eventos, sem apagar dados.

**CI do histórico — commit `145655c`:** SQLite 117 passed / 1 skipped; PostgreSQL 16 118 passed; build Vite aprovado.  
**Validação do downgrade seguro — commit `e15e0c2`:** aguardando execução CI desta revisão.

## Próximo passo exato

Continuar a auditoria endpoint a endpoint com foco em vínculo cruzado de entidades (por exemplo, tarefas associadas a vagas globais, operações de candidatura sobre vagas não vinculadas à conta, e qualquer rota que receba IDs de registros privados). Adicionar testes de IDOR negativos onde necessário. Depois executar testes de migração e rollback em PostgreSQL efêmero, sem tocar no banco de produção.
