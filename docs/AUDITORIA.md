# Auditoria do repositório — JobFinder AI

**Data:** 11/11/2026  
**Branch auditada:** `feature/proof-to-opportunity-engine`  
**Commit-base:** `62559f48982616686923b4e396acfb9aa8d7cf02`  
**Escopo:** leitura do código da branch no GitHub; sem acesso ao banco real, sem deploy e sem alteração da `main`.

## Matriz funcional

| Funcionalidade | Situação atual | O que falta | Ação |
|---|---|---|---|
| Currículo PDF/DOCX | Parcial | Consentimento externo por importação, limite de uso e validação do conteúdo no backend | Implementar consentimento explícito, rate limit e validações; preservar revisão manual |
| Perfil profissional | Parcial | Consolidar objetivos, evidências e trilha temporal em uma visão única | Reaproveitar os registros estruturados existentes e completar a experiência |
| Career Twin | Incrementado | Read model determinístico e interface mostram evidências por origem; a linha do tempo agrega formação, experiência, projeto, aprendizado, metas e desafios por conta | Manter derivações explicáveis; ledger persistente e eventos completos de edição ainda não existem |
| Skill Gap | Incrementado | Snapshot × perfil, metadados de período/amostra e diagnóstico por requisito de vaga com origem da evidência | Ampliar taxonomia/contexto e avaliar obrigatoriedade quando descrições forem ambíguas; ausência de menção não é ausência de conhecimento |
| Inteligência de mercado | Incrementado | Snapshots, tamanho de amostra, comparabilidade e diferenças em pontos percentuais entre dois snapshots com filtros/versões equivalentes | Ainda falta agendamento quinzenal real e histórico de cada observação/publicação da vaga; tendência não é previsão |
| Plano de desenvolvimento | Parcial | Itens e status pertencem à conta, mas conclusão não forma ainda um ciclo completo e rastreável até nova evidência | Vincular atividades a evidências e eventos antes de declarar atualização automática do Career Twin |
| Desafios | Parcial | Desafios e checklist são autoavaliação; não há runner ou revisão humana independente | Manter avaliação automática claramente indisponível; não executar código do usuário |
| Autenticação | Implementada no núcleo | Revisão adicional de configuração, expiração e operação de e-mail | Preservar Argon2, sessão opaca, cookies e recuperação de senha |
| Multiusuário | Parcial, fail-closed | Campos de propriedade e consultas escopadas existem; há testes com duas contas; dados legados podem permanecer sem proprietário e o gate bloqueia acesso por padrão | Não habilitar `MULTITENANT_READY` antes de auditoria endpoint a endpoint e schema válido |
| Candidaturas | Parcial | Pipeline e histórico existem; envio real depende de canal externo e métricas ainda precisam de regras de suficiência | Preservar aprovação, limite diário, compatibilidade mínima e confirmação real |
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
8. O envio de lembretes usa destinatário SMTP legado global e está bloqueado no SaaS para evitar envio entre contas. Não habilitar esse fluxo antes da configuração por usuário.

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
