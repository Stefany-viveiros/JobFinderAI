# Decisões técnicas — JobFinder AI

Atualizado em: 12/11/2026  
Branch de trabalho: `feature/proof-to-opportunity-engine`

Este documento registra decisões de segurança e produto tomadas durante a finalização do MVP. Nenhuma decisão autoriza deploy, alteração na `main` ou acesso ao banco de produção.

## 1. Segurança e liberação multiusuário

1. **Fail closed:** manter `MULTITENANT_READY=false` até que todos os testes de isolamento estejam executados e aprovados. Não alterar esse padrão como atalho para liberar a interface.
2. **Identidade:** o identificador do usuário deve vir exclusivamente da sessão autenticada validada pelo backend (`request.state.user_id` ou dependência equivalente). Campos `user_id` enviados pelo cliente nunca são fonte de autorização.
3. **Dados globais e privados:** oportunidades coletadas podem ser compartilhadas como catálogo; perfil, compatibilidade, favoritos, candidaturas, tentativas, tarefas, configurações e evidências são sempre escopados ao usuário.
4. **Legado:** registros sem proprietário não devem ser atribuídos automaticamente à primeira conta criada. Qualquer migração de propriedade exige procedimento explícito, auditável e backup.
5. **CSRF:** manter token CSRF associado à sessão e exigir validação em toda operação que altera estado. CORS não substitui CSRF.
6. **Cookies:** produção exige HTTPS e cookie `Secure`; desenvolvimento local pode usar configuração explícita apropriada. Não enfraquecer atributos em produção.
7. **Rate limiting:** limites de autenticação devem permanecer no servidor e não depender de memória do processo, para funcionar com mais de um worker.
8. **Segredos:** chaves de IA e SMTP permanecem exclusivamente no backend. Nunca registrar tokens, senhas, conteúdo integral de currículos ou credenciais em logs.

## 2. Currículos e provedores de IA

1. Aceitar somente PDF e DOCX, com limite de bytes aplicado durante a leitura (não apenas após carregar o arquivo inteiro), extensão/MIME conferidos e tratamento de arquivos inválidos, criptografados ou excessivamente complexos.
2. Não persistir o arquivo original por padrão.
3. A extração e a análise por IA são sugestões para revisão humana. Nenhuma informação sugerida será persistida sem confirmação explícita.
4. Não enviar currículo a provedor externo sem configuração explícita e transparência. A alternativa sem chave deve permanecer local/determinística.
5. Não interpretar menção de tecnologia como proficiência comprovada. A origem da evidência e seu contexto devem permanecer visíveis.

## 3. Career Twin e diagnóstico

1. Reaproveitar os registros existentes de formação, experiências, cursos, certificações e projetos.
2. Evidências devem indicar fonte, registro de origem e trecho que sustenta a competência, quando disponível.
3. Estados de evidência não equivalem a níveis de proficiência. Ausência de menção significa “não identificada nos registros disponíveis”, não “não sabe”.
4. Pontuação de compatibilidade é heurística explicável, não probabilidade de contratação. Requisitos desejáveis ausentes não devem eliminar oportunidades.
5. Métricas de mercado devem sempre informar período, nível considerado, tamanho da amostra e limitações da coleta. Comparações temporais exigem períodos equivalentes e amostra suficiente.

## 4. Desafios e evidências

1. Não executar código, comandos, notebooks ou repositórios enviados por usuários na API ou no worker atual.
2. Até existir infraestrutura de execução isolada, a avaliação automática permanece desabilitada e deve ser rotulada como “não disponível”.
3. Autoavaliações, links informados e evidências revisadas por pessoa devem ser identificados pelo tipo e não apresentados como validação independente.
4. Atualizações do Career Twin e recálculos derivados devem preservar a origem e o histórico do evento que os motivou.

## 5. Candidaturas

1. Preservar a política atual de aprovação, limite diário, compatibilidade mínima e confirmação manual.
2. Preparar uma candidatura não significa enviá-la. O estado “enviada” exige confirmação manual explícita ou confirmação do canal de envio real.
3. Textos de candidatura só podem utilizar informações existentes no perfil; não inventar experiências, resultados ou competências.

## 6. Banco e migrações

1. SQLite permanece como banco local/teste e PostgreSQL como opção de produção.
2. Migrações devem ser aditivas e não destrutivas. Não remover colunas, tabelas ou dados legados sem plano de migração e backup.
3. Não executar migrações nem operações no banco de produção durante esta tarefa.
4. A validação do schema multiusuário deve falhar de forma fechada quando constraints necessárias estiverem ausentes ou constraints globais antigas ainda existirem.

## 7. Limitação operacional desta auditoria

A inspeção foi realizada por leitura dos arquivos da branch no GitHub. O ambiente desta sessão não conseguiu clonar o repositório porque não há resolução de rede para `github.com`. Portanto, não é tecnicamente possível afirmar que `pytest -q`, `npm run build` ou testes de integração foram executados localmente nesta sessão. Nenhuma alteração de código deve ser considerada validada sem esses comandos em um checkout real.

## 8. Auditoria inicial — 11/11/2026

| Área | Estado observado no código/documentação | Próxima verificação |
|---|---|---|
| Autenticação | Implementada: Argon2, sessão opaca, recuperação de senha | Testes de ciclo de vida e concorrência |
| Isolamento | Parcial: middleware fail-closed e campos `user_id` em entidades privadas | Auditoria endpoint a endpoint e teste com duas contas |
| CSRF | Implementado no middleware para métodos de escrita | Cobrir todas as rotas, origens e sessão expirada |
| Rate limiting | Implementado para rotas de autenticação | Cobrir upload e operações caras |
| Upload | Extração PDF/DOCX e limite documentado de 5 MB | Confirmar limite no streaming, MIME, extensão e estrutura do arquivo |
| Career Twin | Serviço determinístico com evidências de origem | Estados ambíguos e evidências detalhadas na interface |
| Skill Gap | Serviço de cruzamento com snapshot e perfil | Requisitos obrigatórios/desejáveis por vaga |
| Plano | Serviços e modelos existentes | Vincular conclusão a evento/evidência |
| Desafios | Autoavaliação existente; runner não implementado | Exibir avaliação automática como indisponível |
| Candidaturas | Agente, aprovação, limite e histórico existentes | Testar regressões e métricas do painel |
| Mercado | Snapshot e métricas existentes | Comparação equivalente e relatório quinzenal |
| Migrações | `init_db` contém alterações aditivas; Alembic configurado | Validar histórico Alembic em SQLite e PostgreSQL |
| Documentação | README contém trechos desatualizados sobre autenticação e publicação | Atualizar após validação do código e dos testes |


## 9. Importação de currículo — privacidade e abuso

**Contexto:** a implementação anterior acionava o Gemini sempre que `GEMINI_API_KEY` estava configurada, sem consentimento específico na importação, e não limitava tentativas desse endpoint.

**Alternativas consideradas:** (a) manter envio automático com base apenas na existência da chave; (b) exigir consentimento por importação e manter extração local como padrão.

**Decisão:** adotar (b). A autorização externa vem desmarcada por padrão na interface e é transmitida como campo de formulário. O backend só chama Gemini quando a chave existe e `allow_external_ai=true`. Sem consentimento, usa o extrator local. O backend também aplica limite de cinco importações por conta por hora, valida extensão, MIME quando informado, assinatura inicial PDF/DOCX e o limite de 5 MB.

**Consequências:** pessoas que desejarem análise Gemini devem autorizar explicitamente cada solicitação. A limitação de tentativas é persistida na tabela de rate limit existente, sem serviço externo ou nova dependência. A validação de assinatura é uma barreira básica, não uma análise antivírus nem garantia contra arquivos maliciosos; bibliotecas de leitura continuam sujeitas a atualizações de segurança.


## 10. Diagnóstico por requisito de oportunidade

**Contexto:** a compatibilidade original retornava score e motivos gerais, sem relacionar cada tecnologia citada na descrição a uma origem concreta no perfil.

**Alternativas:** (a) usar apenas comparação de palavras e score; (b) apresentar um diagnóstico por requisito com origem e trecho, sem inferir proficiência.

**Decisão:** implementar `diagnose_job_requirements` e `GET /api/jobs/{job_id}/diagnosis`. O acesso é permitido somente quando a vaga está vinculada ao JobMatch da conta. A classificação obrigatório/desejável utiliza marcadores explícitos na frase; conflitos são ambíguos e ausência de marcador é não especificado. As origens são retornadas separadamente para experiência, projeto, curso, certificação, formação, campo legado, declaração e autoavaliação.

**Consequências:** uma menção prova apenas que a informação aparece no registro; não é uma validação de proficiência. Descrições livres podem produzir classificação incorreta ou incompleta; a interface mostra aviso e não substitui a leitura humana.

## 11. Linha do tempo do Career Twin

**Contexto:** o serviço mostrava competências e evidências, mas não consolidava a evolução em uma trilha visual.

**Decisão:** construir a linha do tempo como read model derivado de registros existentes: educação, experiências, projetos, cursos, certificações, metas e desafios. Eventos de conclusão e autoavaliação são rotulados separadamente e não são transformados em prova independente. Campos de data ausentes permanecem vazios/“Data não informada”.

**Consequências:** não foi criada tabela duplicada nem um ledger persistente. Alterações passadas de um registro não são reconstituídas. Projetos ainda não têm campo de data próprio no schema.

## 12. Tendências de mercado entre snapshots

**Contexto:** snapshots imutáveis existiam, mas a UI não comparava séries históricas.

**Decisão:** implementar `compare_market_trends` e `GET /api/market/trends`. Apenas snapshots concluídos com período, níveis, mínimo de amostra e versões de taxonomia/extrator equivalentes entram no mesmo grupo. O delta é exibido em pontos percentuais. O endpoint retorna indisponibilidade quando há menos de dois snapshots comparáveis.

**Consequências:** não mistura janelas nem versões incompatíveis. A variação é descritiva, não preditiva. Não há agendador quinzenal ativo; a geração de snapshots segue manual até configurar infraestrutura de execução recorrente.


## 13. Histórico das etapas de candidatura

**Contexto:** o modelo `Application` mantinha apenas a etapa atual e a data de atualização, sem permitir reconstruir a sequência de entrevista, teste técnico, aprovação ou encerramento.

**Alternativas:** (a) inferir o histórico a partir de `updated_at` e notas; (b) criar uma tabela aditiva de eventos, sem fabricar eventos anteriores.

**Decisão:** criar `ApplicationEvent` e a migração Alembic `20261112_0002`. O backend registra a etapa inicial quando uma candidatura é criada após o recurso, as transições feitas pela pessoa usuária e a origem do envio por SMTP ou confirmação manual. O endpoint `GET /api/applications/{application_id}/history` valida primeiro a titularidade da candidatura e filtra novamente por `user_id`. A tela de Candidaturas permite abrir a linha do tempo.

**Consequências:** os registros históricos existentes permanecem intocados; não são reconstruídos por inferência. Eventos são imutáveis pela API. A migração é aditiva; downgrade só remove uma tabela vazia e se recusa a continuar quando há eventos.

## 14. Proteção do runner de lembretes global

**Contexto:** a rota HTTP de notificações já estava bloqueada no modo multiusuário, mas o script legado do Agendador chamava diretamente `send_daily_reminder`, que consultava tarefas globais e usava `SMTP_TO` compartilhado.

**Decisão:** bloquear o serviço de envio também quando `MULTITENANT_READY=true`, antes de consultar tarefas ou abrir conexão SMTP.

**Consequências:** o agendador local permanece disponível no modo individual; no modo multiusuário, lembretes só poderão ser liberados após configuração e envio individual por conta.

## 15. Limites de arquivo DOCX

**Contexto:** o tamanho comprimido do upload não limita o volume que um pacote ZIP pode expandir durante a leitura.

**Decisão:** validar o pacote DOCX antes de chamar a biblioteca de documentos: número de entradas, nomes duplicados, presença dos componentes essenciais, criptografia, tamanho de cada entrada, volume total descompactado e taxa de compressão.

**Consequências:** essa é uma defesa de consumo de recursos, não um antivírus ou sandbox. O limite binário de upload permanece 5 MB; o texto extraído continua limitado a 60 mil caracteres.


## 16. Autoavaliação vinculada ao plano e avaliação automática indisponível

**Contexto:** o Career Twin apresentava a autoavaliação de um desafio, mas não deixava visível a meta do plano relacionada; a interface também precisava comunicar claramente a ausência de runner.

**Alternativas:** (a) apresentar a autoavaliação como validação; (b) manter a classificação de autoavaliação, relacionar a meta quando houver vínculo e declarar a indisponibilidade de execução automática.

**Decisão:** incluir `plan_item_id` na evidência derivada do desafio e no detalhe do evento da linha do tempo. A interface mostra a meta vinculada. A página de desafios informa que avaliação automática de código não está disponível e que os arquivos/códigos enviados não são executados.

**Consequências:** a relação é rastreável quando o desafio foi criado a partir de uma meta. Não cria evidência independente, não atribui proficiência e não executa código do usuário. O ledger persistente e a validação por avaliador permanecem pendentes.

## 17. Navegação por módulos sem duplicação de telas

**Contexto:** as capacidades de Career Twin, Skill Gap, desafios e plano já existiam em duas páginas React principais, mas a navegação não refletia os módulos do produto.

**Alternativas:** (a) criar páginas independentes com novos estados e chamadas duplicadas; (b) expor atalhos para as seções dos componentes existentes.

**Decisão:** reorganizar o menu lateral e reutilizar `CareerTwinPage` e `MarketIntelligencePage`, com rolagem para as seções de competências, diagnóstico, desafios e plano.

**Consequências:** reduz duplicação e preserva APIs e estados atuais. Os módulos Competências/Diagnóstico/Desafios/Plano são pontos de entrada para seções existentes, não subsistemas independentes. O painel de candidaturas mostra contagens reais, mas não estima conversão sem amostra/coorte suficiente.
