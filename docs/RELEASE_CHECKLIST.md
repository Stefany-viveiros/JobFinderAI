# Checklist de Release Candidate — JobFinder AI

**Branch de trabalho:** feature/proof-to-opportunity-engine  
**Estado:** preparação; não autorizado para produção.

Este checklist separa validação de código de ativação operacional. Marcar um item como concluído exige evidência no ambiente correspondente.

## 1. Código e CI

- [x] Testes backend SQLite no CI.
- [x] Testes backend PostgreSQL 16 no CI.
- [x] Build de produção do frontend no CI.
- [x] Runner de snapshots falha de forma segura quando o schema não corresponde à revisão Alembic esperada.
- [x] Runner de snapshots não executa migrações nem cria tabelas.
- [x] Workflow de snapshots restrito ao branch padrão.
- [ ] Reexecutar CI após os commits desta atualização documental/workflow.

## 2. Banco de staging — não executar contra produção

- [ ] Identificar explicitamente o banco de staging e confirmar que há backup/cópia descartável.
- [ ] Executar scripts/preflight_release.py com DATABASE_URL do staging.
- [ ] Executar também com --require-multitenant somente após corrigir os bloqueios estruturais.
- [ ] Inspecionar registros sem proprietário; não atribuir automaticamente linhas legadas a usuários.
- [ ] Validar upgrade Alembic e rollback em banco efêmero/cópia controlada, preservando dados.
- [ ] Manter MULTITENANT_READY=false até aprovação formal da auditoria operacional.

## 3. Segredos e serviços — configuração pelo painel, nunca pelo chat

- [ ] Gerar RESUME_STORAGE_KEY e cadastrá-la no serviço hospedado.
- [ ] Gerar SMTP_CREDENTIALS_KEY e cadastrá-la no serviço hospedado.
- [ ] Definir SMTP_ALLOWED_HOSTS com provedores realmente suportados.
- [ ] Configurar MARKET_DATABASE_URL como secret do GitHub Actions somente quando houver banco de mercado autorizado e branch padrão pronto.
- [ ] Confirmar CORS, domínio HTTPS, cookies seguros e política de sessão no ambiente alvo.
- [ ] Não colocar senhas, tokens ou chaves em issues, commits, logs ou mensagens.

## 4. E-mail e candidaturas — etapa final

- [ ] Confirmar o provedor de e-mail da conta antes de escolher SMTP/OAuth.
- [ ] Configurar credencial específica de aplicação ou mecanismo OAuth suportado; nunca usar a senha normal da conta como senha SMTP.
- [ ] Salvar credencial individual na tela de configurações do JobFinder AI.
- [ ] Importar currículo e optar explicitamente por armazená-lo cifrado para candidaturas por e-mail.
- [ ] Testar conexão e envio somente para endereço de teste controlado, com autorização explícita.
- [ ] Validar anexo correto, integridade SHA-256, limites diários, histórico e tratamento de falha.
- [ ] Não enviar candidaturas reais sem aprovação/autorização explícita da titular.

## 5. Limites funcionais conhecidos

- Nem todo portal brasileiro oferece API ou permite candidatura automatizada. Para portais sem canal autorizado, o produto deve abrir o fluxo oficial para conclusão manual; não contornar CAPTCHA, autenticação ou termos do portal.
- Desafios não executam código enviado pelo usuário. Um runner só poderá ser adicionado com isolamento descartável, sem rede e com limites testados.
- O agendamento de snapshots de mercado não equivale a agendamento individual de candidaturas ou notificações.
- Testes automatizados não substituem testes ao vivo de provedores externos, staging, observabilidade e validação de privacidade.

## 6. Aprovação de release

- [ ] Auditoria endpoint a endpoint encerrada e registrada.
- [ ] Testes de integração adicionais e testes de fontes externas concluídos.
- [ ] Staging validado com dados de teste e sem dados legados órfãos.
- [ ] Segredos e serviços configurados por pessoa autorizada.
- [ ] Teste E2E de SMTP aprovado em endereço de teste.
- [ ] Plano de rollback, backup e monitoramento revisados.
- [ ] Aprovação explícita antes de merge na main, migração de banco ou deploy.
