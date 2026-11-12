# Progresso — JobFinder AI Proof-to-Opportunity Engine

**Branch:** `feature/proof-to-opportunity-engine`  
**Último commit registrado:** `05ae7fbc33608f0ad8cd2ab0c869172afb9d718e`.  
**Última atualização:** 11/11/2026.

## Estado retomável

- [x] Conferir a branch de desenvolvimento e o commit-base.
- [x] Ler o README, modelos, serviços, rotas de API, frontend, migrations, testes e configuração de deploy.
- [x] Criar `docs/DECISOES.md` e registrar decisões de segurança.
- [x] Criar a matriz `docs/AUDITORIA.md`.
- [x] Concluir endurecimento do endpoint de importação de currículo.
- [x] Revalidar a suíte SQLite/PostgreSQL e o build no CI para o incremento de privacidade.
- [ ] Ampliar testes de isolamento e revisar todas as rotas pessoais.
- [ ] Evoluir Career Twin, diagnóstico por vaga, plano/eventos e inteligência de mercado.
- [ ] Revisar README, configuração e critérios finais de publicação, sem efetuar deploy.

## Fases e critérios

| Fase | Estado | Critério pendente ou evidência |
|---|---|---|
| A — Auditoria | Concluída | Matriz salva em `docs/AUDITORIA.md`; código lido no GitHub |
| B — Privacidade e segurança da importação | Incremento concluído | Consentimento explícito, limite de uso, validação básica de arquivo e CI aprovado; revisão global de autorização segue aberta |
| C — Career Twin e evidências | Parcial | Serviço e página existentes; falta linha do tempo completa e ligação com eventos |
| D — Diagnóstico por vaga | Parcial | Skill Gap de mercado existe; falta explicação por requisito obrigatório/desejável |
| E — Plano e desafios | Parcial | Plano e autoavaliação existem; falta ciclo rastreável de evidência |
| F — Candidaturas | Parcial | Agente e pipeline existem; falta painel completo com métricas suficientes |
| G — Inteligência de mercado | Parcial | Snapshots manuais existem; falta relatório quinzenal e comparação equivalente |
| H — Qualidade e entrega | Parcial | CI SQLite/PostgreSQL/build está configurado; gate multiusuário permanece fechado; sem deploy |

## Decisões já tomadas

1. Não criar aplicação nova nem duplicar perfil, Skill Gap, plano ou agente.
2. Não alterar a `main`, não executar deploy e não acessar o banco de produção.
3. Manter `MULTITENANT_READY=false` até auditoria completa de rotas, schema e testes de isolamento.
4. Não atribuir dados legados sem proprietário automaticamente a qualquer conta.
5. O Career Twin permanece derivado e explicável; menção textual não equivale a proficiência.
6. A ausência de menção é “não identificada nos registros disponíveis”, nunca “não sabe”.
7. Desafios permanecem autoavaliação; execução de código não está disponível.
8. Dados de currículo só podem ser enviados ao Gemini mediante consentimento explícito por importação. Sem consentimento, usar extração local.
9. Rate limit de importação: cinco envios por usuário por hora, reutilizando o bucket persistente já existente.

## Evidência de qualidade — commit 05ae7fbc

GitHub Actions: execução `43140897026` concluída com sucesso.

- SQLite: 101 testes passaram; 1 ignorado.
- PostgreSQL 16: 102 testes passaram.
- Frontend: build de produção Vite aprovado.

O primeiro commit da implementação falhou em dois testes novos devido a escapes incorretos na assinatura ZIP do DOCX e na expectativa de quebra de linha. O código foi corrigido no commit `05ae7fbc`; a execução seguinte passou integralmente. Os avisos de depreciação das bibliotecas/frameworks permanecem registrados no log e não foram tratados como falhas.

## Próximo passo exato

Ampliar os testes de IDOR para confirmar que uma segunda conta não consegue aprovar nem cancelar tentativas de candidatura da primeira. Depois continuar a revisão endpoint a endpoint das rotas privadas e registrar qualquer lacuna encontrada antes de avaliar a liberação de `MULTITENANT_READY`.
