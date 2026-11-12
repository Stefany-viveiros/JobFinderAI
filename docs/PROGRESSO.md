# Progresso — JobFinder AI Proof-to-Opportunity Engine

**Branch:** `feature/proof-to-opportunity-engine`  
**Último commit registrado:** a ser atualizado após o incremento de privacidade do currículo.  
**Última atualização:** 11/11/2026.

## Estado retomável

- [x] Conferir a branch de desenvolvimento e o commit-base.
- [x] Ler o README, modelos, serviços, rotas de API, frontend, migrations, testes e configuração de deploy.
- [x] Criar `docs/DECISOES.md` e registrar decisões de segurança.
- [x] Criar a matriz `docs/AUDITORIA.md`.
- [ ] Concluir endurecimento do endpoint de importação de currículo.
- [ ] Revalidar a suíte SQLite/PostgreSQL e o build no CI para o novo commit.
- [ ] Ampliar testes de isolamento e revisar todas as rotas pessoais.
- [ ] Evoluir Career Twin, diagnóstico por vaga, plano/eventos e inteligência de mercado.
- [ ] Revisar README, configuração e critérios finais de publicação, sem efetuar deploy.

## Fases e critérios

| Fase | Estado | Critério pendente ou evidência |
|---|---|---|
| A — Auditoria | Concluída | Matriz salva em `docs/AUDITORIA.md`; código lido no GitHub |
| B — Privacidade e segurança da importação | Em implementação | Consentimento explícito, limite de uso, validação de arquivo e testes de regressão |
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

## Próximo passo exato

Executar a suíte completa no GitHub Actions para o commit do endurecimento de importação. Se algum job falhar, ler os logs do job, corrigir a implementação (sem afrouxar ou remover testes) e criar um novo commit em português. Só então avançar para a revisão endpoint a endpoint do isolamento multiusuário.
