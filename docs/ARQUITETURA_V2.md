# JobFinder AI 2.0 — Arquitetura e plano de evolução

## Objetivo

Evoluir o JobFinder AI de uma ferramenta local de busca e organização de vagas para uma plataforma web com um agente de recrutamento autônomo, execução em segundo plano, candidaturas automáticas permitidas, inteligência adaptativa e orientação de desenvolvimento profissional.

## Decisões de produto

- Modelo operacional: agente autônomo.
- Política de candidatura: envio automático quando todos os critérios forem atendidos.
- Compatibilidade mínima inicial: 80%, configurável.
- Limite diário inicial: até 15 candidaturas, configurável; é um teto, não uma meta.
- Perfil: preservar evidências reais e distinguir formação, experiência profissional, cursos, certificações e projetos.
- Aprendizado: ajustar a priorização do matching com base em resultados observados e recomendar trilhas de desenvolvimento.
- Segurança: filtros obrigatórios e limites não podem ser alterados pelo mecanismo adaptativo.
- Integridade: nunca inventar experiência, domínio técnico, certificados, datas ou respostas. Não contornar CAPTCHA, login, controles anti-bot ou termos de plataformas. Quando a plataforma exigir ação humana ou não oferecer canal autorizado, criar pendência manual em vez de simular envio.
- Auditoria: registrar decisões, pontuações, versões de pesos, tentativas, resultado real e motivo de bloqueio.

## Estado atual verificado no repositório

A branch `main` já contém:
- Frontend React + Vite e backend FastAPI.
- Persistência SQLite com SQLAlchemy.
- Coleta por Remotive, Arbeitnow, OkEmprego e Nerdin.
- Filtros de estágio/júnior e área de tecnologia, deduplicação e matching determinístico.
- Importação de currículo PDF/DOCX, com extração local de fallback e análise opcional via Gemini.
- Preparação de candidaturas, histórico de tentativas e envio automático somente por SMTP quando a descrição publica um e-mail de contato.
- Execução pontual do agente por `python -m jobfinder.agent_runner`.

A branch `feature/importacao-curriculo` (PR #3) acrescenta perfil estruturado para múltiplas formações, experiências, cursos, certificações e projetos, além de editor e extração estruturada. O GitHub Actions dessa branch reportou sucesso para testes do backend e build de produção do frontend. O PR permanece aberto; portanto, essa evolução ainda não faz parte da `main`.

Limitações atuais:
- Não há autenticação multiusuário nem isolamento de dados por conta.
- O banco padrão é SQLite local.
- Não há worker de nuvem continuamente ativo.
- O agente não tem aprendizado adaptativo nem módulo de lacunas de competências.
- As fontes atuais não oferecem candidatura automática por API; o envio real está limitado ao e-mail SMTP publicado na vaga. Indeed e Vagas.com não estão integrados para coleta automática.

## Arquitetura-alvo

### Apresentação
- React + Vite.
- Áreas: Dashboard, Vagas, Candidaturas, Agente, Inteligência de carreira, Perfil e Configurações.
- Estados do agente: ativo, pausado, interrompido, aguardando intervenção e erro.

### API e domínio
- FastAPI + Pydantic.
- Autenticação e autorização por usuário.
- Serviços de domínio separados para perfil, vagas, matching, candidaturas, aprendizado, notificações e auditoria.
- Endpoints versionados e documentação OpenAPI.

### Agente e execução assíncrona
- Orquestrador que coordena coleta, normalização, deduplicação, elegibilidade, matching, preparação, envio e acompanhamento.
- Redis + Celery para filas e workers.
- Agendador para ciclos recorrentes.
- Idempotência para impedir envios duplicados, retries controlados e fila de intervenção humana.
- Kill switch global e por usuário.

### Persistência
- PostgreSQL gerenciado como banco principal.
- SQLAlchemy com migrações versionadas (Alembic).
- Armazenamento privado de arquivos para currículos, com acesso restrito e política de retenção.
- Redis apenas para filas/cache, não como fonte definitiva dos dados.

### Inteligência
- Matching explicável e híbrido: regras determinísticas + análise semântica assistida por IA.
- Elegibilidade separada da pontuação: critérios eliminatórios nunca podem ser compensados por uma nota alta.
- Aprendizado adaptativo baseado em amostras suficientes e resultados observáveis; versionar pesos, limitar alterações e permitir rollback.
- Skill Gap Analysis baseada na frequência dos requisitos das vagas compatíveis e nas evidências do perfil.
- Trilhas de aprendizagem com progresso verificável; concluir conteúdo não equivale automaticamente a dominar uma competência.

### Observabilidade e segurança
- Logs estruturados, métricas, rastreamento de execuções e alertas.
- Segredos somente em variáveis seguras do ambiente/secret manager.
- Proteção de dados pessoais, controle de acesso, rate limiting e backups.
- Auditoria de toda ação externa e resultado de envio confirmado pelo provedor/canal.

## Política de decisão de candidatura

1. Validar se a vaga é do tipo, nível, área, localidade e modalidade aceitos.
2. Verificar requisitos obrigatórios com evidência no perfil; requisito obrigatório não comprovado bloqueia o envio automático.
3. Calcular compatibilidade e exigir o mínimo configurado (inicialmente 80%).
4. Verificar duplicidade, candidatura anterior, limite diário, estado do agente e permissão do canal.
5. Gerar documentos e mensagens usando apenas fatos comprovados no perfil.
6. Validar destinatário, anexos, links e conteúdo antes do envio.
7. Enviar somente por canal oficial/permitido e registrar o resultado real.
8. Se houver CAPTCHA, login interativo, pergunta desconhecida, consentimento, expectativa salarial não definida ou outro passo que exija decisão humana, suspender a candidatura e criar pendência.
9. Registrar motivo de aprovação, bloqueio, falha ou intervenção manual.

## Modelo de aprendizado

### Aprendizado adaptativo
- Registrar impressões, candidaturas, respostas, entrevistas e resultados, distinguindo "sem resposta" de rejeição explícita.
- Não ajustar pesos com base em uma única observação.
- Controlar tamanho mínimo de amostra, janela temporal e confiança.
- Manter pesos-base, pesos candidatos, histórico de versões e rollback.
- O algoritmo pode reordenar oportunidades; não pode relaxar requisitos eliminatórios, mudar preferências explícitas nem inventar competências.

### Inteligência de carreira
- Comparar requisitos recorrentes das vagas-alvo com competências comprovadas.
- Agrupar lacunas por prioridade, frequência, relevância e esforço estimado.
- Recomendar conteúdo, exercícios e projetos práticos.
- Registrar progresso como "estudando", "praticado" ou "validado"; apenas evidência ou confirmação atualiza o perfil profissional.

## Fases de implementação

1. Auditoria, estabilização e consolidação do perfil estruturado.
2. Modelo de dados, migrações Alembic e política de elegibilidade.
3. Matching explicável, feedback e histórico de versões de pesos.
4. Skill Gap Analysis e trilhas de aprendizagem.
5. Orquestrador, filas, agendador, idempotência e execução autônoma.
6. Conectores de candidatura permitidos, com intervenção humana quando necessário.
7. Autenticação, isolamento multiusuário, PostgreSQL e armazenamento privado.
8. Interface de controle, observabilidade, segurança e publicação.
9. Testes integrados, testes de carga, piloto controlado e liberação gradual.

## Critérios de aceite

- Nenhuma candidatura pode ser marcada como enviada sem confirmação real do canal.
- Nenhum requisito obrigatório ausente pode ser compensado pela pontuação.
- Nenhuma candidatura duplicada pode ser enviada.
- Limite diário e kill switch são aplicados no servidor, não apenas na interface.
- Toda decisão do agente é explicável e auditável.
- O aprendizado adaptativo pode ser revertido e não altera regras obrigatórias.
- Dados e currículos de usuários diferentes permanecem isolados.
- Testes automatizados e build de produção passam antes de cada merge.
