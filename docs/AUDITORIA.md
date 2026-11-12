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
| Career Twin | Parcial | O serviço determinístico já cruza registros e taxonomia; a interface mostra resumo e competências, mas a linha do tempo detalhada é limitada | Evoluir o read model e a interface sem criar cópia do perfil |
| Skill Gap | Parcial | A comparação principal é snapshot de mercado × registros do perfil; ainda não há diagnóstico completo por requisito de cada vaga | Integrar evidência por requisito, obrigatoriedade, contexto e recomendação |
| Inteligência de mercado | Parcial | Snapshot manual já existe, com níveis e tamanho de amostra; falta relatório quinzenal automatizado e comparação robusta de períodos equivalentes | Preservar snapshots, evidenciar período e amostra, só comparar janelas equivalentes |
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
2. A suíte já possui testes de isolamento com duas contas para perfil, tarefas, candidaturas, tentativas, configurações do agente, plano, desafios, notificações e Career Twin. Ainda é necessário manter essa cobertura para cada nova rota pessoal e ampliar casos de IDOR.
3. Várias entidades privadas possuem `user_id`, mas parte dos campos legados é nullable. Dados sem proprietário não podem ser automaticamente associados à primeira conta.
4. O catálogo de vagas e as análises de mercado são globais; perfil, score privado, favoritos, candidaturas, tarefas, plano e avaliações são escopados por usuário. Essa fronteira deve permanecer explícita.
5. Antes deste incremento, o endpoint de importação acionava Gemini apenas pela presença de `GEMINI_API_KEY`, sem consentimento por solicitação, e não possuía rate limit específico.
6. O upload já limitava leitura a 5 MB e não persistia o arquivo original. Ainda faltavam validação de assinatura/MIME e limite de tentativas. A validação de assinatura adicionada é defesa básica, não antivírus.
7. A autenticação usa Argon2, token de sessão aleatório com hash persistido, cookie HttpOnly e token CSRF. O cookie seguro e o HTTPS precisam permanecer alinhados à configuração de produção.
8. O envio de lembretes usa destinatário SMTP legado global e está bloqueado no SaaS para evitar envio entre contas. Não habilitar esse fluxo antes da configuração por usuário.

### Integridade do produto

1. O Career Twin é um read model derivado; não há ledger persistente de cada evidência nem histórico completo de eventos para reconstruir todas as transições.
2. A classificação de competência indica origem textual/contextual. Projeto concluído, curso ou certificação não comprovam isoladamente proficiência.
3. O Skill Gap atual usa snapshot de mercado e perfil; ainda não explica, requisito a requisito, todas as vagas e sua distinção entre obrigatório e desejável.
4. Snapshots são criados por solicitação manual. A automação quinzenal ainda depende de agendador/serviço de execução e de amostra real.
5. A avaliação de desafios é autoavaliação; o runner seguro não existe. Não executar código enviado por usuário.
6. Candidaturas preparadas não equivalem a enviadas. O agente pode enviar por e-mail somente quando o fluxo real e as configurações permitem; demais canais continuam manuais.

### Dívida técnica e documentação

1. O README anterior dizia que a aplicação não oferecia autenticação multiusuário, embora a branch já tivesse sessões, middleware e testes de isolamento.
2. A configuração de demonstração não equivale a um SaaS pronto para receber dados pessoais reais.
3. A taxonomia determinística tem cobertura limitada aos termos e aliases cadastrados; ausência de menção não implica ausência de conhecimento.
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
