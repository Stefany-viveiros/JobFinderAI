# Market Intelligence — especificação técnica inicial

## 1. Objetivo e escopo

O módulo transforma as vagas de estágio e júnior em tecnologia já coletadas pelo JobFinder AI em indicadores verificáveis sobre a demanda do mercado. O foco inicial é Brasil e oportunidades de estágio/júnior; filtros por área, modalidade, localização, fonte e período devem permitir recortes sem misturar níveis diferentes.

O módulo também compara a demanda observada com as evidências do perfil profissional e sugere prioridades de desenvolvimento. Não é uma plataforma de cursos e não deve afirmar que a pessoa domina ou desconhece uma tecnologia sem evidência.

## 2. Estado atual e limites conhecidos

A aplicação já possui:
- React + Vite e FastAPI.
- SQLAlchemy e SQLite local.
- Fontes implementadas: Remotive, Arbeitnow, OkEmprego e Nerdin.
- Filtro de estágio/júnior em tecnologia e deduplicação por URL normalizada e título + empresa.
- Vagas com título, empresa, descrição, fonte, tipo, nível classificado, data de publicação (texto da fonte) e `created_at` (primeiro registro local).
- Perfil estruturado com formações, experiências, cursos, certificações e projetos.

Já implementado na branch `feature/market-intelligence`:
- Catálogo canônico inicial de competências com aliases/sinônimos.
- Extração determinística e persistência de evidências por vaga.
- Snapshots de análise, métricas de frequência e combinações de competências.
- Endpoints de análise, histórico, combinações e Skill Gap.
- Página React com filtros, indicadores, ranking, combinações e cruzamento com o perfil.

Ainda não há:
- Histórico de observações de cada vaga em cada coleta; por isso, não há tendência temporal confiável.
- Classificação consistente por subárea (frontend, backend, dados, IA, mobile etc.).
- Avaliação prática ou validação de proficiência por competência.
- Trilhas didáticas completas, curadoria de recursos externos e acompanhamento de proficiência validada.

Limitações de qualidade:
- A descrição fornecida por algumas fontes pode ser resumida ou incompleta; a Nerdin, por exemplo, monta parte da descrição com resumo e hashtags.
- A data de publicação tem formatos diferentes entre fontes e pode estar ausente.
- A deduplicação atual elimina uma vaga repetida entre fontes sem manter uma relação de proveniência entre todas as fontes que a publicaram.
- A tabela Job representa a primeira inserção local, não um histórico de cada observação posterior.

Essas limitações devem aparecer na interface e nos metadados dos relatórios; não se deve apresentar uma amostra parcial como se representasse todo o mercado.

## 3. Princípios de cálculo

1. A unidade estatística é a vaga distinta, não o número de ocorrências da palavra.
2. Uma vaga pode mencionar várias competências; por isso, os percentuais de competências não precisam somar 100%.
3. Taxa de menção = vagas distintas que mencionam a competência / total de vagas distintas válidas no recorte.
4. Sinônimos são agrupados em uma competência canônica (por exemplo, JS/JavaScript; Postgres/PostgreSQL; Node/Node.js).
5. Título, descrição, hashtags e campos estruturados podem servir como evidência, mas a interface deve indicar quando a fonte forneceu descrição incompleta.
6. Frequência não equivale automaticamente a prioridade de estudo. A prioridade deve combinar demanda, aderência à área pretendida, evidência atual no perfil e esforço estimado.
7. Ausência no currículo significa “não identificado no perfil”, não “não sabe”.
8. Não mostrar tendência de alta/queda sem duas janelas comparáveis e amostra suficiente.
9. Sempre mostrar quantidade de vagas, período, nível, fontes, data da última atualização e limitações da amostra.
10. A análise inicial deve ser determinística e auditável; IA pode ser avaliada depois como enriquecimento assistido, nunca como fonte de fatos não verificados.

## 4. Categorias de competência

- Linguagens de programação.
- Frameworks e bibliotecas.
- Bancos de dados.
- Cloud e infraestrutura.
- Ferramentas e plataformas.
- Práticas e metodologias.
- Competências comportamentais (em fase posterior, por depender de extração contextual mais cuidadosa).

A taxonomia deve guardar nome canônico, categoria, aliases/sinônimos, status ativo e versão. Exemplos de aliases:
- JavaScript: JS, ECMAScript.
- TypeScript: TS.
- PostgreSQL: Postgres, Postgre SQL.
- Node.js: Node, NodeJS.
- React: React.js.
- C#: C Sharp.

Não tratar termos ambíguos como competências sem contexto suficiente (ex.: “Go”, “R”, “C”, “.NET”). A lista de termos e regras deve ser testada para evitar falsos positivos, como Java dentro de JavaScript.

## 5. Modelo de dados proposto

### Skill
Catálogo de competências canônicas:
- id
- canonical_name (único)
- category
- aliases (estrutura JSON ou tabela normalizada)
- active
- taxonomy_version
- created_at / updated_at

### JobSkill
Relação entre vaga e competência:
- id
- job_id (FK)
- skill_id (FK)
- evidence_text (trecho curto que justificou a detecção)
- evidence_field (title, description, tags ou structured)
- extraction_method (dictionary, manual ou assisted)
- confidence
- extractor_version
- created_at
- Unique(job_id, skill_id)

### MarketAnalysisRun
Registro imutável de cada análise:
- id
- period_start / period_end
- collected_after / collected_before (janela de primeira observação local)
- level_scope (internship, junior ou both)
- area_scope (inicialmente tecnologia)
- filters_json
- total_jobs
- valid_jobs
- jobs_with_description
- sources_json
- taxonomy_version
- extractor_version
- status (running, completed, failed)
- created_at / completed_at
- quality_notes

### MarketSkillMetric
Métricas congeladas de cada análise:
- id
- run_id (FK)
- skill_id (FK)
- jobs_count
- mention_rate
- rank
- Unique(run_id, skill_id)

### MarketSkillPair
Coocorrência de competências:
- id
- run_id (FK)
- skill_a_id / skill_b_id (FK, ordem canônica)
- jobs_count
- pair_rate
- Unique(run_id, skill_a_id, skill_b_id)

As tabelas de análise guardam snapshots imutáveis. Uma nova execução cria um novo snapshot; não reescreve relatórios anteriores. A relação JobSkill pode ser recalculada quando a versão do extrator mudar, mantendo a versão usada.

## 6. Recortes e filtros

Filtros iniciais:
- Nível: estágio, júnior ou ambos.
- Área: desenvolvimento frontend, backend, full stack, dados, IA/automação, mobile e demais áreas de tecnologia reconhecidas.
- Período: últimos 30, 60 ou 90 dias; intervalo personalizado futuramente.
- Fonte.
- Modalidade e localização quando os dados forem confiáveis.

Não combinar estágio e júnior silenciosamente: mostrar comparativo lado a lado e permitir selecionar cada nível.

## 7. Endpoints propostos

- `POST /api/market/analysis/run`: inicia análise/snapshot com filtros e janela.
- `GET /api/market/analysis/latest`: metadados e métricas da última análise.
- `GET /api/market/analysis/history`: lista de snapshots para comparar períodos.
- `GET /api/market/skills`: catálogo e categorias.
- `GET /api/market/skills/{skill_id}`: detalhe, evidências agregadas e vagas relacionadas.
- `GET /api/market/combinations`: pares de competências mais recorrentes.
- `GET /api/market/profile-gap`: cruzamento entre demanda e evidências do perfil.
- `POST /api/market/skills/{skill_id}/progress`: registrar estudo/prática/validação, sem converter estudo automaticamente em domínio.

Os endpoints devem validar filtros e limitar o volume processado. A primeira versão pode executar a análise de forma síncrona para o volume local; filas e agendamento recorrente ficam para a fase de implantação em nuvem.

## 8. Regras de qualidade e amostra

- Não gerar ranking conclusivo com menos de 30 vagas válidas no recorte. Abaixo disso, exibir “amostra insuficiente” e os números observados sem chamar de tendência.
- Preferir 50 ou mais vagas por recorte para comparações e tendências.
- Exibir vagas totais e vagas com descrição útil; descrição ausente ou curta não pode ser tratada como ausência de tecnologia.
- Deduplicar antes de contar.
- Não somar menções repetidas da mesma competência na mesma vaga.
- Excluir vagas fora do nível/área do recorte.
- Tratar datas ausentes ou não parseáveis separadamente; não inventar data.
- A comparação temporal deve usar janelas equivalentes, mesma taxonomia e filtros compatíveis. Se a taxonomia mudar, registrar a versão e sinalizar a quebra de comparabilidade.

Os limites 30/50 são critérios iniciais de produto, configuráveis após observar o volume real; não são uma afirmação estatística universal.

## 9. Skill Gap e plano de desenvolvimento

Cada competência do perfil deve ter um estado de evidência:
- Evidenciada em experiência profissional.
- Evidenciada em projeto.
- Declarada no perfil/currículo.
- Curso concluído.
- Em estudo.
- Praticada.
- Validada por evidência/avaliação.
- Não identificada no perfil.

O sistema não deve converter “não identificada” em “não sabe”. Cursos e projetos são evidências de contato/prática, não prova automática de domínio avançado.

A prioridade sugerida deve considerar:
- Frequência nas vagas compatíveis com o objetivo (não apenas todas as vagas de tecnologia).
- Recorrência em combinações relevantes.
- Lacuna entre demanda e evidências existentes.
- Relevância para a área escolhida.
- Esforço aproximado e pré-requisitos.

A primeira entrega recomenda trilhas e recursos externos, com metas e registro de progresso. Geração de aulas e exercícios fica para uma etapa posterior.

## 10. Interface proposta

Nova seção na navegação: **Inteligência de mercado**.

Blocos:
1. Resumo da amostra: vagas analisadas, período, níveis, fontes e atualização.
2. Competências mais mencionadas: ranking com quantidade e percentual.
3. Comparativo estágio x júnior.
4. Combinações de tecnologias.
5. Evolução temporal (somente quando houver histórico comparável).
6. Compatibilidade com o perfil: competências evidenciadas, declaradas, em estudo e não identificadas.
7. Plano de desenvolvimento recomendado.

Gráficos e cartões devem manter tipografia legível, percentuais acompanhados de contagens e estados vazios explicativos. Não usar dados fictícios como se fossem reais.

## 11. Etapas de implementação

1. Criar e testar catálogo de competências e extrator determinístico.
2. Persistir JobSkill com evidências e versão do extrator.
3. Implementar execução e snapshots de análise com métricas e coocorrências.
4. Criar endpoints e testes de API/cálculo.
5. Criar a página React e integrar filtros.
6. Implementar cruzamento com perfil e plano de desenvolvimento (primeira versão publicada na branch).
7. Adicionar histórico comparável e agendamento após infraestrutura de execução contínua estar definida.

## 12. Critérios de aceite da primeira versão

- Só vagas válidas de estágio/júnior em tecnologia entram nos recortes.
- Uma vaga conta uma vez por competência, mesmo que repita o termo.
- Sinônimos são agrupados e termos ambíguos não geram falsos positivos silenciosos.
- Toda métrica pode ser explicada por vagas e evidências rastreáveis.
- Percentuais sempre vêm acompanhados de contagens e tamanho da amostra.
- A análise guarda filtros, fontes, período e versões do catálogo/extrator.
- Nenhuma competência ausente é rotulada como desconhecida ou não dominada.
- Nenhum dado ilustrativo aparece como dado real.
- Testes do backend e build de produção do frontend passam antes do merge.


## 13. Implementação inicial publicada na branch

A primeira fatia do backend foi adicionada à branch `feature/market-intelligence`:

- `jobfinder/market.py`: taxonomia inicial e extração determinística com evidência.
- `jobfinder/market_service.py`: sincronização do catálogo, indexação idempotente por vaga e criação de snapshots com métricas e coocorrências.
- `jobfinder/models.py`: tabelas `market_skills`, `job_market_skills`, `job_skill_extractions`, `market_analysis_runs`, `market_skill_metrics` e `market_skill_pairs`.
- `jobfinder/api.py`: endpoints para executar análise, consultar última análise, histórico e combinações.
- `tests/test_market.py` e `tests/test_market_service.py`: testes unitários e de persistência.

Endpoints disponíveis nesta etapa:
- `POST /api/market/analysis/run` com `level_scope` (`both`, `estagio`, `junior`) e `days`.
- `GET /api/market/analysis/latest`.
- `GET /api/market/analysis/history`.
- `GET /api/market/combinations` (aceita `run_id` opcional).

A janela temporal usa `jobs.created_at`, que representa quando a vaga foi observada pela primeira vez neste banco. Não equivale necessariamente à data original de publicação. A indexação registra também vagas processadas sem competências reconhecidas, evitando reprocessamento repetitivo.

**Ainda não implementado nesta etapa:** interface React, análise de evolução entre snapshots, skill gap do perfil, plano de desenvolvimento e agendamento em nuvem. Os testes foram adicionados, mas precisam de execução no CI antes de considerar a etapa validada.

## 14. Skill Gap — implementação inicial

A branch agora contém o primeiro cruzamento entre o snapshot de mercado e o perfil profissional:

- `jobfinder/market_service.py`: função `build_profile_gap`, que consulta as competências do snapshot e procura menções no perfil estruturado.
- `GET /api/market/profile-gap` (aceita `run_id` opcional): retorna demanda, quantidade de vagas, percentual, estado da evidência e recomendação de acompanhamento.
- `frontend/src/MarketIntelligencePage.jsx`: seção “Skill Gap: mercado × seu perfil”, com resumo por tipo de evidência e lista de competências.
- `tests/test_market_service.py`: cenário cobrindo competência em projeto, curso concluído, declaração no perfil e a ressalva de ausência de evidência.

Estados identificados:
- Evidenciada em experiência profissional.
- Praticada em projeto concluído.
- Evidenciada em projeto em desenvolvimento.
- Mencionada em curso concluído.
- Mencionada em certificação.
- Em estudo ou prática em andamento.
- Mencionada na formação acadêmica.
- Declarada no perfil.
- Não identificada no perfil.

**Limites:** a primeira versão usa correspondência determinística por aliases no texto cadastrado. Não avalia profundidade, qualidade ou domínio real; curso/projeto/certificação são indícios de contato com a tecnologia. A prioridade exibida usa apenas a posição no ranking observado (top 5) como sinal para avaliação, não como ordem definitiva de estudo. A recomendação deve ser contextualizada pela área de interesse e pelo objetivo profissional da pessoa.

## 15. Plano de desenvolvimento — primeira versão

A primeira versão persistente do plano foi adicionada à branch `feature/market-intelligence`:

- Modelo `DevelopmentPlanItem` na tabela `development_plan_items`, vinculado a uma competência do catálogo e, opcionalmente, ao snapshot que motivou a meta.
- `GET /api/market/development-plan`: lista metas e resumo de progresso.
- `POST /api/market/development-plan`: adiciona uma competência do Skill Gap ao plano, com atividade prática sugerida e estimativa inicial de horas.
- `PATCH /api/market/development-plan/{item_id}`: atualiza status, percentual, prazo, anotações e detalhes da meta.
- `DELETE /api/market/development-plan/{item_id}`: remove uma meta.
- A interface permite adicionar competências do Skill Gap, acompanhar status e progresso, registrar anotações e remover metas.

Estados persistidos: `planned`, `in_progress`, `paused` e `completed`. Marcar como concluída registra 100% e data de conclusão. Uma competência não pode ter duas metas ativas simultâneas; uma meta concluída pode ser refeita posteriormente.

A atividade inicial é um roteiro genérico e determinístico por categoria da taxonomia, não uma trilha didática completa nem uma recomendação de curso verificada. Links de recursos externos não são inventados ou preenchidos automaticamente nesta fase. As horas são estimativas editáveis, não previsões de tempo de aprendizagem.

**Validação pendente:** os testes de serviço foram adicionados, mas ainda precisam ser executados no ambiente do projeto; também falta confirmar o build de produção do frontend e a criação da tabela em uma instalação com banco existente. O fluxo atual usa `Base.metadata.create_all` na inicialização; uma estratégia formal de migrações continua recomendada para o deployment.
