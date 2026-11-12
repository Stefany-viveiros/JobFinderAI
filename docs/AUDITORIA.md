# Auditoria do repositório — JobFinder AI

**Data:** 12/11/2026  
**Branch auditada:** `feature/proof-to-opportunity-engine`  
**Commit-base:** `62559f48982616686923b4e396acfb9aa8d7cf02`  
**Escopo:** leitura do código da branch no GitHub; sem acesso ao banco real, sem deploy e sem alteração da `main`.

## Matriz funcional

| Funcionalidade | Situação atual | O que falta | Ação |
|---|---|---|---|
| Currículo PDF/DOCX | Incrementado | Consentimento explícito para Gemini, extração local padrão, cinco importações/hora, limite 5 MB, validação de assinatura/estrutura e barreira contra DOCX ZIP expansivo | Manter atualização de bibliotecas e considerar antivírus/limite de CPU em infraestrutura; não tratar validação básica como antivírus |
| Perfil profissional | Parcial | Consolidar objetivos, evidências e trilha temporal em uma visão única | Reaproveitar os registros estruturados existentes e completar a experiência |
| Career Twin | Incrementado | Read model determinístico e interface mostram evidências por origem; a linha do tempo agrega formação, experiência, projeto, aprendizado, metas e desafios por conta | Manter derivações explicáveis; ledger persistente e eventos completos de edição ainda não existem |
| Skill Gap | Incrementado | Snapshot × perfil, metadados de período/amostra e diagnóstico por requisito de vaga com origem da evidência | Ampliar taxonomia/contexto e avaliar obrigatoriedade quando descrições forem ambíguas; ausência de menção não é ausência de conhecimento |
| Inteligência de mercado | Incrementado | Snapshots, tamanho de amostra, comparabilidade e diferenças em pontos percentuais entre dois snapshots com filtros/versões equivalentes | Ainda falta agendamento quinzenal real e histórico de cada observação/publicação da vaga; tendência não é previsão |
| Plano de desenvolvimento | Parcial | Itens e status pertencem à conta, mas conclusão não forma ainda um ciclo completo e rastreável até nova evidência | Vincular atividades a evidências e eventos antes de declarar atualização automática do Career Twin |
| Desafios | Parcial | Desafios e checklist são autoavaliação; não há runner ou revisão humana independente | Manter avaliação automática claramente indisponível; não executar código do usuário |
| Autenticação | Implementada no núcleo | Revisão adicional de configuração, expiração e operação de e-mail | Preservar Argon2, sessão opaca, cookies e recuperação de senha |
| Multiusuário | Parcial, fail-closed | Campos de propriedade e consultas escopadas existem; há testes com duas contas; dados legados podem permanecer sem proprietário e o gate bloqueia acesso por padrão | Não habilitar `MULTITENANT_READY` antes de auditoria endpoint a endpoint e schema válido |
| Candidaturas | Incrementado | Pipeline, aprovação, limite diário, compatibilidade mínima e histórico imutável de mudanças de etapa por conta; migração Alembic aditiva | Completar métricas de conversão com amostra suficiente; histórico só conta a partir da ativação e não recupera etapas anteriores |
| Agente de candidaturas | Implementado com limites | Envio automático só é real para e-mail/SMTP elegível; plataformas externas exigem ação manual | Não ampliar automação além de canais permitidos; registrar falhas reais |
| Fontes de vagas | Parcial | Remotive, Arbeitnow, OkEmprego e Nerdin têm coleta; Indeed e Vagas.com são links de busca/manual | Monitorar erros e deduplicação; não simular coleta indisponível |
| Deploy | Parcial | Render + Neon configurados como demonstração; não liberar workspace antes do gate de segurança | Manter read-only, sem deploy ou acesso a banco de produção nesta tarefa |
| Migrações | Parcial | Há migração Alembic para unicidade por usuário e alterações aditivas em inicialização; falta validar upgrade/rollback em ambientes reais controlados | Testar SQLite e PostgreSQL em CI; nunca executar contra produção nesta tarefa |
| Interface React | Implementada, parcialmente integrada | Já existem páginas para Career Twin, Mercado e Agente; navegação e estados podem ser refinados | Reaproveitar páginas e componentes; cobrir estados vazios, erro e carregamento |
| CI | Implementado | Workflows cobrem pytest em SQLite/PostgreSQL e build do Vite | Continuar usando CI como evidência após cada commit |

## Achados técnicos e riscos

### Segurança

1. O middleware exige sessão e CSRF para operações de escrita nas rotas privadas. O acesso à área autenticada fica bloqueado com HTTP 503 enquanto `MULTITENANT_READY` não estiver explicitamente habilitado; essa proteção não deve ser removida como atalho.
2. A suíte possui testes de isolamento entre duas contas para perfil, tarefas, candidaturas, tentativas, configurações do agente, plano, desafios, notificações e Career Twin; há também testes negativos para aprovar/cancelar tentativas de outra conta, gate fechado e escrita sem CSRF. Ainda é necessária revisão endpoint a endpoint de todas as rotas pessoais.
3. Várias entidades privadas possuem `user_id`, mas parte dos campos legados é nullable. Dados sem proprietário não podem ser automaticamente associados à primeira conta.
4. O catálogo de vagas e as análises de mercado são globais; perfil, score privado, favoritos, candidaturas, tarefas, plano e avaliações são escopados por usuário. Essa fronteira deve permanecer explícita.
5. Antes deste incremento, o endpoint de importação acionava Gemini apenas pela presença de `GEMINI_API_KEY`, sem consentimento por solicitação, e não possuía rate limit específico.
6. O upload já limitava leitura a 5 MB e não persistia o arquivo original. Ainda faltavam validação de assinatura/MIME e limite de tentativas. A validação de assinatura adicionada é defesa básica, não antivírus.
7. A autenticação usa Argon2, token de sessão aleatório com hash persistido, cookie HttpOnly e token CSRF. O cookie seguro e o HTTPS precisam permanecer alinhados à configuração de produção.
8. O envio de lembretes usa destinatário SMTP legado global e está bloqueado tanto na rota HTTP quanto no runner do Agendador quando `MULTITENANT_READY=true`. Não habilitar esse fluxo antes da configuração por usuário.
9. A migração de histórico de candidaturas é aditiva; o downgrade recusa apagar a tabela quando existem eventos, preservando os dados.

### Integridade do produto

1. O Career Twin é um read model derivado; não há ledger persistente de cada evidência nem histórico completo de eventos para reconstruir todas as transições.
2. A classificação de competência indica origem textual/contextual. Projeto concluído, curso ou certificação não comprovam isoladamente proficiência.
3. O Skill Gap compara snapshot e perfil; o endpoint `/api/jobs/{job_id}/diagnosis` agora explica competências identificadas por requisito, incluindo origem, trecho e classificação textual de obrigatoriedade/desejabilidade. A taxonomia não cobre todas as expressões possíveis.
4. Snapshots são criados por solicitação manual. O endpoint `/api/market/trends` compara dois snapshots concluídos apenas quando período, nível, taxonomia e extrator são equivalentes. A execução quinzenal automática ainda depende de agendador/serviço contínuo configurado.
5. A avaliação de desafios é autoavaliação; o runner seguro não existe. Não executar código enviado por usuário.
6. Candidaturas preparadas não equivalem a enviadas. O agente pode enviar por e-mail somente quando o fluxo real e as configurações permitem; demais canais continuam manuais.

### Dívida técnica e documentação

1. O README anterior dizia que a aplicação não oferecia autenticação multiusuário, embora a branch já tivesse sessões, middleware e testes de isolamento.
2. A configuração de demonstração não equivale a um SaaS pronto para receber dados pessoais reais.
3. A taxonomia determinística tem cobertura limitada aos termos e aliases cadastrados; ausência de menção não implica ausência de conhecimento. O diagnóstico classifica requisito obrigatório/desejável somente quando há marcadores textuais claros e sinaliza conflitos como ambíguos.
4. Não foi possível verificar comportamento de fontes externas em tempo real nesta auditoria sem executar as coletas. Testes automatizados não garantem disponibilidade contínua dos provedores.

## Evidências de qualidade disponíveis no commit-base

No commit `62559f4`, o GitHub Actions concluiu com sucesso:
- Backend tests (SQLite).
- Backend tests (PostgreSQL 16).
- Frontend production build.

Esses resultados pertencem ao commit-base e não validam alterações posteriores. A execução local de `pytest -q` e `npm run build` nesta sessão não foi possível porque o checkout local do repositório não está disponível; novas alterações devem ser validadas pelo GitHub Actions antes de serem consideradas concluídas.

## Prioridade de execução

1. Endurecer upload e privacidade de currículo — incremento iniciado nesta branch.
2. Verificar e fechar brechas de isolamento por endpoint com testes de duas contas.
3. Completar evidências e timeline do Career Twin.
4. Evoluir diagnóstico por vaga, mantendo score explicável.
5. Integrar plano, desafios e eventos sem executar código.
6. Evoluir painel de candidaturas e relatório de mercado.
7. Atualizar documentação, configuração de produção e critérios de aceite sem deploy.


## Atualização após auditoria — commit 05ae7fbc

O incremento de privacidade do upload foi implementado em `jobfinder/api.py` e `frontend/src/App.jsx`:
- A permissão de envio ao Gemini passou a ser explícita por importação e desmarcada por padrão.
- A extração local é mantida quando não há autorização externa.
- Há limite persistente de cinco importações por usuário por hora.
- O backend verifica extensão, tipo MIME quando informado, assinatura inicial PDF/DOCX e máximo de 5 MB.
- Foram adicionados testes para consentimento, conteúdo DOCX inconsistente e limite por conta.

**CI do commit `05ae7fbc33608f0ad8cd2ab0c869172afb9d718e`:** SQLite 101 passed / 1 skipped; PostgreSQL 16 102 passed; build Vite aprovado. A suíte já continha testes de isolamento entre duas contas; novos testes específicos de tentativa de aprovação/cancelamento cruzado ainda serão adicionados na revisão de autorização.


## Atualização após implementações de 12/11/2026

### Career Twin e diagnóstico por vaga

- `jobfinder/career_twin.py` compõe uma linha do tempo por usuário com educação, experiência, projeto, curso, certificação, metas do plano e desafios/autoavaliações.
- Eventos de conclusão de meta não são promovidos a competência comprovada.
- A interface mostra datas ausentes explicitamente; o schema ainda não tem data para projeto, então esses eventos não são posicionados artificialmente no tempo.
- `GET /api/jobs/{job_id}/diagnosis` exige vínculo da vaga com o JobMatch da conta, relaciona competências à origem textual e apresenta a classificação obrigatório/desejável com aviso de ambiguidade.

### Inteligência de mercado

- O Skill Gap informa período, nível e quantidade de vagas, além do mínimo configurado e suficiência da amostra.
- `GET /api/market/trends` compara os dois snapshots concluídos mais recentes do mesmo recorte, janela e versões de taxonomia/extrator.
- O frontend exibe delta em pontos percentuais e sinaliza amostra insuficiente.
- A página inclui cookies de sessão e CSRF para chamadas de escrita; a consulta de tendência tem fallback visual para indisponibilidade temporária.
- Não há coleta recorrente quinzenal ativa. Snapshot continua sendo solicitado pelo usuário.

**CI do commit `56c067e032ab0314db94ea5245253ff5649f57f9`:** SQLite 111 passed / 1 skipped; PostgreSQL 16 112 passed; frontend Vite build aprovado. Execução: `43145152234`.

### Limitações que permanecem

- O Career Twin é um read model, não um ledger versionado de evidências; alterações antigas de perfil não podem ser reconstruídas como eventos.
- Projetos não possuem campos de data no schema; eventos de projeto aparecem com data não informada.
- Classificação de requisito é baseada em marcadores e frases, não em compreensão semântica completa.
- Tendências dependem de snapshots manuais e de registros locais de primeira coleta; não equivalem a projeção de mercado.


## Atualização de segurança e candidaturas — 12/11/2026

- O serviço de lembrete legado agora também bloqueia execução direta do Agendador do Windows quando `MULTITENANT_READY=true`; a proteção não depende apenas da rota HTTP.
- O parser DOCX valida estrutura ZIP, quantidade de entradas, tamanho máximo de cada entrada, tamanho total descompactado e taxa de compressão antes de abrir o documento.
- `application_events` registra mudanças de etapa da candidatura com `user_id`, candidatura, status anterior/novo, origem, anotação e data.
- O endpoint de histórico verifica a propriedade da candidatura e filtra também cada evento pela conta autenticada.
- O downgrade da revisão `20261112_0002` interrompe quando existem eventos e não elimina o histórico.
- O frontend permite consultar o histórico no painel de candidaturas e informa que eventos antigos não são reconstruídos.

**CI do commit `145655c856ca9cd7c4d4ef60cfecff69164fb4ce`:** SQLite 117 passed / 1 skipped; PostgreSQL 16 118 passed; build Vite aprovado. Execução: `43147354689`.


## Atualização — 12/11/2026: autorização por oportunidade e schema

- Ações sobre vagas globais agora exigem vínculo ativo em `JobMatch` para a conta: favoritar, preparar candidatura, confirmar candidatura e associar tarefa.
- O teste de duas contas cobre tentativas negativas e ausência de efeitos colaterais.
- O validador de startup agora verifica as tabelas privadas, FKs de propriedade, linhas sem proprietário e unicidade composta por conta.
- CI validado no commit `b0bce8f`: SQLite 121 passed / 1 skipped; PostgreSQL 16 122 passed; build Vite aprovado.
- Ainda não se declara a auditoria integral concluída. Permanecem a revisão de rotas/configurações e a validação operacional de migrações/dados legados em cópia controlada. `MULTITENANT_READY=false` continua obrigatório.


## Atualização — 12/11/2026: registros de perfil e rollback PostgreSQL

- O sincronizador de registros estruturados (formação, experiência, cursos, certificações e projetos) recebe a coleção já carregada pela relação do perfil autenticado; IDs desconhecidos na coleção não são usados para buscar nem alterar registros de outro perfil. Teste de duas contas confirma que enviar ID estrangeiro cria/atualiza somente registro próprio e preserva o registro original.
- A revisão das rotas privadas identificou escopo por conta nas operações de candidatura, tentativas, tarefas, plano, avaliações, notificações, configurações e histórico. As rotas de mercado consultam snapshots agregados derivados de vagas públicas; não leem conteúdo pessoal de perfil.
- Testes PostgreSQL efêmeros cobrem criação/FKs da tabela `application_events`, proteção contra rollback com eventos existentes e proteção contra downgrade da unicidade por usuário quando a mesma vaga está associada a contas diferentes.
- CI do commit `82d60c1`: SQLite 121 passed / 2 skipped; PostgreSQL 16 123 passed; build Vite aprovado.
- A auditoria endpoint a endpoint ainda não está encerrada: falta validar operacionalmente configuração e migrações do schema completo em cópia controlada, revisar rotinas legadas e planejar a resolução explícita de dados sem proprietário. O gate multiusuário permanece fechado.


## Atualização — 12/11/2026: configuração CORS

- A API agora valida `CORS_ORIGINS` no startup e rejeita wildcard com credenciais/cookies, HTTP remoto, caminhos, query/fragment, userinfo e portas inválidas.
- Origens locais HTTP são permitidas somente para localhost/loopback; origens remotas devem usar HTTPS. Entradas duplicadas são normalizadas.
- A configuração inválida interrompe o startup com erro explícito, evitando uma política CORS permissiva silenciosa.
- CI do commit `1ac6407`: SQLite 131 passed / 2 skipped; PostgreSQL 16 133 passed; build Vite aprovado.
- Essa validação cobre a lista de origens configurada, não substitui a configuração correta do domínio real no ambiente de hospedagem. Não houve alteração em Render ou Neon.


## Atualização — 12/11/2026: configuração de sessão e cookie

- Configuração de sessão centralizada e validada no startup: ambiente permitido, duração entre 1 e 720 horas e booleano estrito para `COOKIE_SECURE`.
- Staging/production recusam inicialização com `COOKIE_SECURE=false`; a autenticação usa os valores já validados.
- `render.yaml` declara `APP_ENV=production`, `COOKIE_SECURE=true` e `SESSION_HOURS=24`; `.env.example` demonstra configuração local separada.
- CI do commit `e12d575`: SQLite 141 passed / 2 skipped; PostgreSQL 16 143 passed; build Vite aprovado.
- Alteração apenas no repositório; sem deploy e sem alteração de variáveis no serviço hospedado.


## Atualização — 12/11/2026: runners agendados legados

- Identificado que `agent_runner.main()` chamava `init_db()` e executava o agente sem identidade de conta. Agora bloqueia antes do banco quando `MULTITENANT_READY=true`.
- Identificado que `reminder_runner.main()` inicializava o banco antes de chegar ao bloqueio existente em `send_daily_reminder`. Agora também bloqueia antes de `init_db` e `SessionLocal`.
- Testes verificam explicitamente que nenhum dos runners inicializa o banco ou abre sessão no modo multiusuário.
- CI do commit `f4f5f6f`: SQLite 143 passed / 2 skipped; PostgreSQL 16 145 passed; build Vite aprovado.
- Agendamento individual por conta, com limites e SMTP individual, permanece pendente. Os runners globais não devem ser ativados no SaaS.


## Teste de integração CORS — 12/11/2026

- Teste de preflight verifica origem permitida (localhost) com credenciais e origem externa não cadastrada recusada pelo middleware.
- CI do commit `efab261`: SQLite 144 passed / 2 skipped; PostgreSQL 16 146 passed; build Vite aprovado.
