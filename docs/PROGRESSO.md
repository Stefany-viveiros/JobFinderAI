# Progresso — JobFinder AI Proof-to-Opportunity Engine

**Branch:** `feature/proof-to-opportunity-engine`  
**Último commit de implementação:** `c32a736`  
**Atualização:** 12/11/2026.  \n**Cobertura geral estimada:** 90% (estimativa de escopo, não métrica automatizada).

## Estado de execução

| Fase | Estado | Evidência / pendência |
|---|---|---|
| A — Auditoria | Concluída | Matriz em `docs/AUDITORIA.md`; frontend, API, modelos, serviços, migrações, testes e deploy revisados na branch |
| B — Segurança e privacidade | Incrementos concluídos; liberação SaaS pendente | Consentimento explícito para Gemini, upload endurecido, rate limit, CSRF e testes de isolamento; gate continua fechado |
| C — Career Twin | Incremento concluído | Read model, linha do tempo e Ledger persistente versionado; revisão humana com observação, histórico append-only, exclusão de evidência irrelevante do Career Twin/diagnóstico e consulta isolada por conta. Gate de schema também valida FKs, proprietário, revisões órfãs e vínculos cruzados; CI aprovado em SQLite, PostgreSQL 16 e Vite |
| D — Diagnóstico de oportunidades | Incremento concluído | Endpoint por vaga com classificação de requisitos e rastreabilidade de evidências; não mede proficiência; CI aprovado |
| E — Desenvolvimento e desafios | Parcial, com evidências persistentes | Desafios enviados geram evidência `self_assessed` vinculada à tentativa e à competência. Continua sem execução de código ou validação independente; UI deixa essa limitação explícita |
| F — Candidaturas e agente | Histórico concluído; métricas parciais | Pipeline e política do agente preservados; histórico por evento/conta no backend e frontend. Painel mostra totais, entrevistas, andamento e aprovações; taxa de conversão não é exibida sem base temporal/coorte suficiente. Métricas de retorno e cobertura das fontes ainda pendentes |
| G — Inteligência de mercado | Incremento concluído | Snapshot, Skill Gap com contexto de amostra e comparação de dois snapshots equivalentes; agendamento recorrente ainda depende de infraestrutura |
| H — Qualidade e entrega | Parcial, sem deploy | CI do código aprovado no commit `c32a736`; documentação atualizada; navegação modular, upload DOCX endurecido e migrações aditivas. `main`, Render e Neon permanecem intocados |

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

- Varredura estática de todos os handlers concluída e documentada; faltam testes de integração adicionais nas rotas críticas e validação operacional do schema/dados legados em cópia controlada.
- Validar upgrades/rollbacks Alembic em cópia controlada de banco e revisar os registros sem `user_id`.
- Definir agendador recorrente real para snapshots de mercado (por exemplo, job/cron compatível com infraestrutura contratada); não há execução quinzenal automática ativa.
- Completar análise de candidaturas com métricas de conversão sem inferir resultados inexistentes.
- Ledger persistente e revisão humana implementados e documentados; CI anterior aprovado. A proteção do gate multiusuário para revisões cruzadas está em validação.
- Não implementar runner de código até existir isolamento descartável, sem rede e com limites testados.
- Revisar configuração de e-mail por usuário; o destinatário SMTP global não deve ser liberado no SaaS.
- Atualizar e validar a configuração de produção somente após aprovação de segurança.

## Próximo passo exato

Fechar a validação do gate de schema e preparar checklist de release candidate. A varredura estática de rotas e o ensaio de migração em banco efêmero estão documentados; manter `MULTITENANT_READY=false` até resolver dados legados e configurações por conta.


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


## Atualização de 12/11/2026 — navegação, desafios e validação final desta rodada

- Navegação lateral reorganizada para: Visão geral, Oportunidades, Agente, Candidaturas, Meu Career Twin, Competências, Diagnóstico, Desafios, Mercado, Plano, Tarefas e Configurações. Os itens reaproveitam os componentes existentes; não criam telas com dados fictícios.
- Atalhos Competências e Diagnóstico rolam até as seções existentes correspondentes.
- A autoavaliação de desafio passa a carregar o identificador da meta vinculada na evidência do Career Twin e no evento da linha do tempo.
- A página de desafios informa que avaliação automática de código não está disponível e que código enviado não é executado no servidor.
- A área de candidaturas mantém contagens observáveis (total, entrevistas, andamento e aprovadas). Não foi adicionada taxa de conversão porque os dados atuais não sustentam uma coorte temporal confiável.
- Commits desta rodada: `ab4390e` (isolamento do diagnóstico por conta), `b1f52ed` (vínculo desafio/meta e transparência do runner), `df711fd` (navegação modular), `7f03180` (correção do menu) e `e61097b` (âncora do diagnóstico).
- CI do commit `e61097b`: SQLite **119 passed, 1 skipped**; PostgreSQL 16 **120 passed**; build de produção Vite **success**. Warnings reportados são avisos, não falhas.

## Pendências para liberação de uso multiusuário/produção

- Revisão endpoint a endpoint ainda não é considerada encerrada; manter `MULTITENANT_READY=false`.
- Não executar deploy nem alterar banco de produção nesta entrega.
- Antes de ativar multiusuário: auditar rotas privadas remanescentes, revisar dados legados sem proprietário e validar migrações em cópia controlada.
- A automação quinzenal de mercado ainda exige agendador externo; o botão/manual e comparação de snapshots existentes não equivalem a agendamento ativo.
- O ledger persistente de evidências e a validação independente de desafios continuam fora do escopo concluído; não há execução de código de usuário.
- A taxa de conversão de candidaturas permanece oculta até existir base de candidaturas suficientemente madura e comparável.


## Incremento de auditoria de isolamento — 12/11/2026

- Identificado que as rotas de favoritar, preparar candidatura, confirmar candidatura e criar tarefa associada verificavam a existência global da vaga sem exigir vínculo ativo em `JobMatch` para a conta autenticada.
- Criado o helper `_require_user_job_match`, que exige vínculo por `user_id` e vaga não arquivada antes dessas operações.
- Removida a criação implícita de `JobMatch` ao favoritar um ID global arbitrário; a operação agora só altera um vínculo que já pertence à conta.
- Criado teste negativo cobrindo tarefa, favorito, candidatura manual e preparação de candidatura contra vaga vinculada somente a outra conta. Também verifica que as tentativas negadas não criam tarefas, candidaturas ou tentativas.
- Commits: `2de88e6` (correção) e `72617a2` (teste de IDOR).
- CI do commit `72617a2`: SQLite **120 passed, 1 skipped**; PostgreSQL 16 **121 passed**; build Vite **success**. Warnings são depreciações já reportadas; a mensagem PostgreSQL de chave duplicada aparece no teste de unicidade e não falhou a suíte.

**Próximo passo:** continuar a revisão de todas as rotas que aceitam IDs globais ou relacionados e verificar as operações de perfil/configuração e o vínculo de entidades legadas. O gate `MULTITENANT_READY=false` permanece obrigatório até encerrar a revisão completa e validar o schema.


## Incremento de validação do schema multiusuário — 12/11/2026

- `validate_multitenant_schema` agora verifica a presença de tabelas privadas e colunas `user_id`, FKs para `users.id`, registros sem proprietário e unicidade por conta em `applications`, `job_matches`, `profile` e `agent_settings`.
- Registros legados com `user_id` nulo fazem a inicialização falhar de forma explícita; não são atribuídos automaticamente a nenhuma conta.
- Teste de regressão confirma que um schema limpo passa e que a presença de uma tarefa legada sem proprietário bloqueia a validação.
- Commits: `e28ffa7` (validador) e `b0bce8f` (teste).
- CI do commit `b0bce8f`: SQLite **121 passed, 1 skipped**; PostgreSQL 16 **122 passed**; build Vite **success**. Warnings são avisos de depreciação; a mensagem de chave duplicada no log PostgreSQL é gerada pelo teste de unicidade e a suíte terminou com sucesso.

**Situação:** o gate continua `MULTITENANT_READY=false`. A validação do schema agora é mais completa, mas isso não substitui a auditoria integral de cada rota nem a resolução operacional dos dados legados em qualquer banco de destino.


## Continuação da auditoria de autorização e migrações — 12/11/2026

- Revisadas as rotas privadas e as operações com IDs: candidaturas, tentativas, tarefas, metas e avaliações usam escopo por usuário; diagnóstico, favorito, preparação/envio e tarefa associada exigem vínculo ativo da oportunidade; o histórico de candidaturas verifica propriedade da candidatura e dos eventos.
- Os endpoints de snapshots, histórico, tendências e combinações de mercado leem dados agregados de vagas públicas e taxonomia, sem dados pessoais de perfil. Permanecem atrás do middleware de sessão; não são endpoints públicos anônimos.
- O sincronizador de registros estruturados do perfil usa apenas a coleção pertencente ao perfil autenticado. Teste de regressão agora simula tentativa de alterar formação de outra conta com ID conhecido e comprova que o registro original não muda.
- Adicionado teste PostgreSQL para upgrade da migração de histórico de candidaturas, validação de FKs e rollback: o downgrade recusa apagar eventos existentes e, após remoção controlada do evento no schema efêmero, reverte a tabela vazia.
- Adicionado teste PostgreSQL para impedir downgrade da unicidade por usuário quando duas contas já se candidataram à mesma vaga; confirma que os registros e a constraint composta permanecem após a recusa.
- CI do commit `82d60c1`: SQLite **121 passed, 2 skipped**; PostgreSQL 16 **123 passed**; build Vite **success**. Os skips do SQLite incluem cenários exclusivos do PostgreSQL. Warnings são avisos; a mensagem de chave duplicada é esperada no teste de unicidade.

**Pendente:** auditoria operacional das configurações de implantação e migrações sobre uma cópia controlada do schema completo; revisar rotinas agendadas/administrativas legadas e validar plano de tratamento de registros sem proprietário. O gate `MULTITENANT_READY=false` continua obrigatório.


## Endurecimento de configuração CORS — 12/11/2026

- Adicionado `parse_cors_origins` para validar a lista explícita de origens permitidas.
- Wildcard `*` é recusado porque a API usa cookies/credenciais; origens remotas exigem HTTPS; HTTP fica restrito a localhost/loopback.
- Caminhos, query strings, fragmentos, credenciais embutidas e portas inválidas são recusados; origens repetidas são normalizadas.
- A API falha no startup com mensagem clara quando `CORS_ORIGINS` está inseguro ou malformado, em vez de iniciar com uma política permissiva.
- Testes unitários cobrem origens válidas, duplicadas e entradas inseguras/inválidas.
- Commits: `dac4ccf`, `d08c819`, `baf2090`, `791c0d5`, `af66f40`, `1ac6407`.
- CI do commit `1ac6407`: SQLite **131 passed, 2 skipped**; PostgreSQL 16 **133 passed**; build Vite **success**.

**Próximo passo:** revisar configurações de sessão/cookie e variáveis obrigatórias de produção, depois validar a migração completa e o bootstrap em schema PostgreSQL efêmero. Não alterar o ambiente Render/Neon de demonstração.


## Validação da configuração de sessão — 12/11/2026

- Centralizada a configuração de sessão em `jobfinder.config`: `APP_ENV`, `SESSION_HOURS` e `COOKIE_SECURE`.
- `SESSION_HOURS` precisa estar entre 1 e 720; `APP_ENV` aceita somente development, test, staging ou production; `COOKIE_SECURE` aceita somente true/false.
- Staging e production exigem `COOKIE_SECURE=true`; configurações inválidas interrompem a inicialização.
- `auth.py` passou a consumir a configuração validada, evitando interpretações divergentes de variáveis de ambiente.
- `.env.example` agora exemplifica HTTP local com cookie não seguro somente em desenvolvimento; `render.yaml` declara explicitamente production, cookie seguro e sessão de 24 horas.
- Testes unitários cobrem valores válidos e recusam ambiente desconhecido, sessão fora do intervalo e cookie inseguro em staging/production.
- CI do commit `e12d575`: SQLite **141 passed, 2 skipped**; PostgreSQL 16 **143 passed**; build Vite **success**.

**Pendente:** revisão operacional da configuração de produção e ensaio de bootstrap completo do schema em banco efêmero. O manifesto foi ajustado no repositório, mas nenhum deploy foi realizado; `MULTITENANT_READY=false` permanece.


## Bloqueio de agendadores globais no modo multiusuário — 12/11/2026

- `jobfinder/agent_runner.py` agora verifica `MULTITENANT_READY` antes de inicializar o banco; quando ativo, retorna e registra bloqueio em log porque o runner legado não recebe identidade de conta.
- `jobfinder/reminder_runner.py` também bloqueia antes de inicializar o banco ou abrir sessão; o envio individual por conta ainda não está implementado.
- Foram adicionados testes que substituem `init_db` e `SessionLocal` por falhas, provando que os runners não acessam o banco no modo multiusuário.
- CI do commit `f4f5f6f`: SQLite **143 passed, 2 skipped**; PostgreSQL 16 **145 passed**; build Vite **success**.

**Implicação:** não habilitar tarefas agendadas globais no SaaS. Próxima evolução futura é um scheduler que itere contas elegíveis, aplique limites individuais e registre cada execução por usuário, com envio SMTP configurado por conta.


## Teste de integração CORS — 12/11/2026

- Além dos testes unitários de parsing, foi adicionado teste de preflight real no middleware FastAPI/Starlette: origem local autorizada recebe CORS com credenciais; origem externa não cadastrada recebe rejeição sem cabeçalho de permissão.
- CI do commit `efab261`: SQLite **144 passed, 2 skipped**; PostgreSQL 16 **146 passed**; build Vite **success**.
- O resultado valida o middleware com a configuração padrão dos testes; o domínio real de produção continua dependendo da variável explícita `CORS_ORIGINS` no serviço hospedado.

## Ledger persistente de evidências — 12/11/2026

- Criada a tabela `career_evidence`, sempre vinculada a `users.id`, com competência, categoria, origem, chave estável da fonte, trecho curto, hash, nível de validação, estado ativo/inativo e data de substituição.
- A sincronização ocorre ao salvar o perfil. Novas fontes recebem IDs antes da geração da chave; atualizações idênticas são idempotentes; mudanças criam nova versão e inativam a anterior; registros removidos deixam de ser ativos sem apagar o histórico.
- O endpoint `GET /api/career-evidence` não aceita `user_id` do cliente e filtra pela conta autenticada.
- O Career Twin apresenta o histórico persistido, inclusive versões anteriores. Autoavaliações de desafios são registradas como `self_assessed`, nunca como validação independente.
- A migração `20261112_0003` é aditiva e impede downgrade com histórico existente.
- Testes cobrem idempotência, versionamento, remoção, isolamento entre contas, autoavaliação e preservação do ledger em rollback.
- Commits desta etapa: `a2e4b69` (modelo), `fddd978` (migração), `4bba430` (sincronização), `c6ce99c` (endpoint), `40ea667` (Career Twin), `46da40e` (testes), `79bf295` / `04ad962` (correções de sincronização), `5c279fd` (teste de rollback), `c486e66` / `bd0a956` / `a160933` (autoavaliação), `ddadab1` (interface do histórico) e `fd6b7c4` (estilos de versões anteriores).
- CI funcional do ledger: [execução 43157143830](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43157143830) — SQLite **146 passed, 2 skipped**; PostgreSQL 16 **148 passed**; build Vite **success**.
- Execução da última alteração visual: [CI 43157232132](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43157232132). Build Vite e SQLite aprovados; PostgreSQL ainda em execução no momento desta atualização.

## Próximos passos

1. Completar a revisão final de isolamento de rotas e operações de conta, mantendo `MULTITENANT_READY=false` até validação integral.
2. Evoluir desafios para uma trilha de validação externa segura; não executar código de usuário no servidor atual.
3. Adicionar interface de revisão e correção das evidências, mantendo a origem e o histórico.
4. Concluir métricas de retorno de candidaturas com dados reais e coortes comparáveis.
5. Implementar agendamento real de snapshots de mercado e notificações individuais, sem reativar runners globais.
6. Validar migrações e schema em banco PostgreSQL efêmero antes de qualquer decisão operacional. Nenhuma migração ou deploy de produção está autorizado nesta etapa.

## Revisão humana do ledger — 12/11/2026

- `POST /api/career-evidence/{evidence_id}/review` registra decisões `confirmed` e `dismissed` em eventos append-only, com observação opcional de até 1.000 caracteres.
- `GET /api/career-evidence/{evidence_id}/reviews` devolve o histórico completo em ordem cronológica e retorna 404 para evidências de outra conta.
- `GET /api/career-evidence` continua apresentando a decisão mais recente, sem alterar `verification_level` ou a evidência original.
- A decisão `dismissed` remove a origem do mapa de competências e do diagnóstico por vaga; autoavaliações descartadas deixam de contar como autoavaliadas quando não há outra tentativa ativa relevante.
- O Career Twin permite adicionar observação, confirmar a origem ou marcar a menção como não relevante e consultar todas as revisões.
- Testes cobrem histórico completo, preservação da evidência original, isolamento entre contas e exclusão efetiva no Career Twin/diagnóstico.
- CI do commit `9156f41`: SQLite **148 passed, 3 skipped**; PostgreSQL 16 **151 passed**; Vite **success**. Execução: [43221321603](https://github.com/Stefany-viveiros/JobFinderAI/actions/runs/43221321603).
- Foi adicionado teste de rollback da migração `20261112_0004`; CI do commit `d63be76` está em execução.
