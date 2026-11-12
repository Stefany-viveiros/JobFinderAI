# Proof-to-Opportunity Engine — especificação de produto e arquitetura

## 1. Visão do produto

O JobFinder AI evolui de uma ferramenta de busca e organização de vagas para uma plataforma de inteligência de carreira orientada por evidências.

**Promessa:** ajudar cada pessoa a entender o que sabe fazer, demonstrar suas competências, identificar lacunas relevantes no mercado e encontrar oportunidades coerentes com evidências reais do seu perfil.

O diferencial não será apenas gerar uma pontuação de compatibilidade. Será manter uma relação rastreável entre o que o mercado solicita, o que a pessoa declara saber, onde a competência aparece no histórico, que tipo de evidência existe e o que ainda precisa ser demonstrado.

O sistema não promete contratação, não certifica proficiência por inferência e não transforma ausência de informação em falta de conhecimento.

## 2. O que já existe e deve ser reaproveitado

A implementação atual já oferece:

- Perfil com formações, experiências, cursos, certificações e projetos estruturados.
- Importação de currículo PDF/DOCX com revisão antes de salvar.
- Catálogo canônico de competências e aliases.
- Evidências de competências extraídas de vagas.
- Snapshots auditáveis de inteligência de mercado.
- Skill Gap entre demanda observada e perfil.
- Plano individual de desenvolvimento.
- Desafios práticos com histórico de autoavaliação.
- Compatibilidade explicável e preparação de candidaturas.
- Autenticação por sessão, proteção CSRF, rate limits e estrutura multiusuário.

Esses recursos serão conectados e evoluídos. Não criaremos módulos duplicados de radar, currículo, Skill Gap ou plano de desenvolvimento.

## 3. Conceito central: Career Twin

O Career Twin é uma representação estruturada, explicável e atualizável do perfil profissional. Não é um chatbot, um currículo alternativo nem uma pontuação única. É uma visão consolidada construída a partir de registros existentes e evidências com origem identificável.

### Dimensões

- Identidade profissional: objetivo, áreas de interesse, nível pretendido e modalidade.
- Formação: cursos acadêmicos, instituição, situação e período.
- Experiência: cargo, organização, período, atividades e resultados descritos.
- Portfólio: projetos, tecnologias, situação, repositório e demonstração.
- Aprendizado: cursos e certificações, distinguindo concluídos dos que estão em andamento.
- Competências: catálogo canônico, aliases, contexto e evidências associadas.
- Desenvolvimento: metas e desafios registrados.
- Mercado: demanda observada por área, nível, período e tamanho da amostra.

### Estados de evidência

Uma competência pode possuir várias evidências simultâneas:

- professional_experience: mencionada em experiência profissional.
- completed_project: demonstrada em projeto marcado como concluído.
- ongoing_project: mencionada em projeto em desenvolvimento.
- completed_course: mencionada em curso concluído.
- certification: associada a certificação cadastrada.
- education: mencionada na formação acadêmica.
- self_declared: declarada no perfil/currículo sem outra evidência identificada.
- self_assessed: associada a desafio autoavaliado pela própria pessoa.
- automated_assessment: aprovada em exercício objetivo executado por runner seguro.
- human_reviewed: revisada por avaliador identificado, quando esse fluxo existir.
- not_found: não identificada nos dados disponíveis; nunca significa que a pessoa não sabe.

A interface deve mostrar origem e permitir abrir o registro que sustenta cada afirmação. Não usar uma nota universal de proficiência na primeira versão. Se houver ordenação, ela deve ser descrita como prioridade de evidência, não como nível técnico.

## 4. Primeiro incremento: Career Twin Read Model

A primeira entrega será uma visão consolidada somente de leitura, derivada dos dados existentes.

**Decisão arquitetural:** não criar uma tabela duplicada de perfil nem persistir um score derivado. Construir um serviço que consulta o perfil autenticado, normaliza competências usando o catálogo atual e retorna evidências com origem.

### Endpoint proposto

- GET /api/career-twin

A resposta deve conter:
- resumo de completude do perfil;
- objetivos profissionais;
- formação, experiências, projetos, cursos e certificações;
- competências canônicas;
- lista de evidências por competência, com tipo, ID e nome do registro de origem, trecho mínimo e status;
- contexto de mercado opcional, com snapshot, janela, nível, amostra e limitações;
- avisos de qualidade e estados vazios.

O exemplo de resposta será definido a partir dos nomes e tipos reais do schema. Não fabricar datas, evidências ou métricas.

### Regras do serviço

1. Toda consulta a dados pessoais usa o user_id autenticado da sessão, nunca um ID fornecido livremente pelo cliente.
2. Não aceitar user_id em query string ou body para escolher o perfil consultado.
3. Consultar somente registros pertencentes ao perfil do usuário autenticado.
4. Normalizar nomes com a taxonomia existente e preservar trechos/origens que justificam cada correspondência.
5. Não inferir proficiência a partir de uma palavra isolada.
6. Diferenciar projeto concluído de projeto em desenvolvimento.
7. Diferenciar curso concluído de curso em andamento.
8. Mostrar autoavaliações separadamente de avaliações automatizadas ou humanas.
9. Se não houver snapshot, o Career Twin continua disponível sem contexto de mercado.
10. Se não houver dados suficientes, retornar estados vazios claros; não preencher com conteúdo fictício.
11. Evitar enviar currículo completo a um provedor de IA para cada leitura do painel. A primeira versão será determinística.

## 5. Segunda etapa: Evidence Ledger

Depois de validar o Read Model, evoluir para um registro de evidências versionado.

A tabela futura skill_evidence deverá considerar:

- id;
- user_id obrigatório;
- skill_id;
- source_type (experience, project, course, certification, education, self_assessment, automated_assessment, human_review);
- source_record_id opcional;
- evidence_text ou referência segura ao trecho de origem;
- verification_method;
- verification_status;
- confidence apenas quando houver método documentado para calculá-la;
- created_at e updated_at;
- versão da regra/extrator que criou a evidência.

Não duplicar conteúdo pessoal sem necessidade. Preferir referência ao registro de origem e trecho mínimo justificável. Alterações no perfil devem permitir reconstruir evidências derivadas. Evidências automáticas não podem ser promovidas a humanas sem revisão explícita.

A migração deverá ser aditiva, testada em SQLite e PostgreSQL, com rollback e preservação de dados.

## 6. Terceira etapa: Proof-to-Opportunity Matching

Evoluir a compatibilidade atual para uma explicação baseada em evidências.

Para cada requisito da vaga, retornar:
- requisito identificado;
- obrigatório ou desejável, quando a descrição permitir classificar;
- evidência correspondente no Career Twin;
- origem e trecho de evidência;
- estado: evidenciado, declarado, em desenvolvimento, não identificado ou ambíguo;
- ação recomendada para esclarecer ou desenvolver a competência.

A pontuação existente permanece como heurística explicável. Não chamar de probabilidade de contratação ou chance de aprovação.

Uma lacuna não deve eliminar automaticamente a vaga quando o requisito for desejável. Requisitos obrigatórios não identificados devem continuar exigindo revisão e impedir envio automático conforme as regras atuais.

## 7. Quarta etapa: Skill Simulator com validação objetiva

Os desafios atuais são autoavaliações. A evolução para avaliação objetiva deve seguir obrigatoriamente a especificação docs/SECURE_CODE_ASSESSMENT.md.

Escopo inicial:
- Python;
- JavaScript/Node.js;
- SQL em banco efêmero.

Código enviado nunca será executado no processo FastAPI, no worker principal ou em ambiente com acesso a banco, arquivos e segredos. A execução exige runner descartável, isolado, sem rede e com limites de CPU, memória, processos, tempo e armazenamento.

Estados de infraestrutura (runner indisponível, timeout e erro) não podem ser tratados como reprovação técnica. Um teste aprovado comprova somente que a solução passou nos casos definidos, não proficiência geral nem certificação.

A funcionalidade permanece desabilitada até que o runner seguro exista e seja testado.

## 8. Quinta etapa: Career Gap e plano adaptativo

Reaproveitar o Skill Gap e o plano de desenvolvimento atuais.

A priorização futura deve considerar conjuntamente:
- demanda observada em vagas válidas;
- área e nível desejados pelo usuário;
- evidências atuais do Career Twin;
- obrigatoriedade do requisito quando identificável;
- qualidade e tamanho da amostra;
- pré-requisitos e esforço estimado.

Não recomendar estudo apenas porque uma tecnologia aparece no ranking geral. Explicar por que a atividade foi sugerida e qual evidência poderá ser produzida ao concluí-la.

## 9. Privacidade, segurança e multiusuário

- Dados pessoais, perfil, plano, avaliações e candidaturas devem permanecer isolados por usuário.
- Dados globais de vagas e snapshots de mercado podem ser compartilhados quando não contiverem dados pessoais.
- Nunca expor evidências de um usuário em respostas de outro.
- Não usar dados de candidatos para treinar modelos externos sem consentimento explícito e política adequada.
- Minimizar dados enviados a provedores de IA e documentar transferências.
- Não persistir currículo original sem necessidade e consentimento.
- Manter autenticação, CSRF, rate limiting e proteção de demonstração.
- Não ativar MULTITENANT_READY em produção sem validação do schema, testes de isolamento e revisão de configuração.
- Toda nova rota pessoal deve obter o usuário pela sessão e possuir testes de acesso cruzado.

## 10. Plano incremental e critérios de aceite

### Fase A — Auditoria e contrato
- Confirmar o estado real da branch main, migrations e gates de multi-tenancy.
- Revisar serviços atuais de perfil, Skill Gap e avaliações.
- Mapear rotas e componentes React existentes.
- Definir o contrato de resposta do Career Twin.

Aceite: nenhum módulo existente duplicado; riscos e pendências documentados.

### Fase B — Career Twin Read Model
- Implementar serviço determinístico e endpoint autenticado.
- Adicionar testes unitários para cada tipo de origem.
- Adicionar testes de isolamento entre duas contas.
- Testar perfil vazio, dados parciais, aliases, múltiplas evidências e ausência de snapshot.

Aceite: cada competência exibida possui origem rastreável; nenhum dado de outra conta é retornado.

### Fase C — Interface Career Twin
- Criar página React usando componentes e padrões existentes.
- Exibir resumo, trajetória, competências e evidências.
- Permitir abrir a origem de cada evidência.
- Exibir estados de carregamento, vazio e erro.
- Não apresentar score de proficiência sem validação.

Aceite: build de produção aprovado e interface acessível/legível.

### Fase D — Matching baseado em evidências
- Relacionar requisitos das vagas às evidências do Career Twin.
- Explicar correspondências e lacunas.
- Preservar regras de aprovação e segurança das candidaturas.

Aceite: testes de regressão para falsos positivos, Java versus JavaScript, requisitos obrigatórios e evidências em projetos.

### Fase E — Runner seguro
- Implementar somente após infraestrutura isolada estar definida.
- Manter feature flag desligada por padrão.
- Testar falhas, limites e isolamento.

Aceite: nenhum código arbitrário executado no processo da API ou com acesso a segredos.

## 11. Fora do escopo da primeira entrega

- Reescrever a arquitetura do JobFinder.
- Criar outro radar de vagas.
- Criar chatbot genérico como diferencial central.
- Gerar certificados próprios sem avaliação confiável.
- Declarar nível de proficiência com base em currículo, frequência de palavras ou autoavaliação.
- Executar código do usuário no servidor principal.
- Enviar candidaturas sem as proteções e aprovações existentes.
- Alterar Render, Neon, variáveis de produção ou dados reais durante a primeira entrega.

## 12. Próxima ação técnica

Iniciar pela Fase A. Antes de alterar modelos ou endpoints, revisar o estado atual de main, o gate MULTITENANT_READY, as migrações Alembic e o escopo por usuário das rotas e serviços de perfil/avaliação.

A primeira implementação será o Career Twin Read Model, sem migração de banco. Só depois dos testes e da validação da interface será considerada a criação do Evidence Ledger persistente.
