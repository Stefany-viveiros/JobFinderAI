# JobFinder AI

**Plataforma inteligente para busca, análise de compatibilidade e desenvolvimento profissional para oportunidades de estágio e nível júnior em tecnologia.**

O JobFinder AI é um projeto de portfólio em evolução que reúne busca de vagas, análise de compatibilidade com o perfil profissional, organização de candidaturas e ferramentas para orientar o desenvolvimento de competências. A proposta vai além de um agregador de vagas: o sistema também cruza competências observadas no mercado com as informações do perfil e ajuda a transformar lacunas identificadas em metas e atividades práticas.

A aplicação evoluiu de uma interface construída com Streamlit para uma arquitetura com **React + Vite no frontend** e **FastAPI no backend**, utilizando Python para a lógica de negócio e SQLite para persistência local.

> **Estado atual:** o projeto está em desenvolvimento e sua execução documentada é local. Ainda não há uma versão pública hospedada para acesso pela internet. A arquitetura de avaliação objetiva de código está documentada como próxima evolução, mas o runner isolado ainda não foi implementado.


## Ambiente de demonstração na nuvem

A configuração inicial para Render + Neon está em [render.yaml](render.yaml). O passo a passo está em [docs/DEPLOYMENT_DEMO.md](docs/DEPLOYMENT_DEMO.md).

**Atenção:** o ambiente público é configurado como somente leitura (`DEMO_READ_ONLY=true`). Não desative essa proteção nem conecte dados pessoais reais enquanto a aplicação não tiver autenticação e autorização por usuário. O banco Neon deve ser novo e exclusivo para a demonstração.

## Funcionalidades

### Busca e organização de vagas
- Coleta de oportunidades por meio das fontes implementadas no backend.
- Indicação de falhas durante a consulta às fontes.
- Cadastro manual de oportunidades.
- Pesquisa textual, filtros por compatibilidade, modalidade e favoritos.
- Ordenação e visualização das oportunidades disponíveis.

### Análise de compatibilidade
- Pontuação de compatibilidade entre o perfil profissional e os requisitos identificados na vaga.
- Escala de compatibilidade de 0 a 100.
- Exibição dos critérios encontrados e dos pontos que precisam ser verificados.
- Possibilidade de atualizar o perfil profissional e recalcular as pontuações.

A pontuação é uma heurística explicável para apoiar a triagem. Não representa probabilidade de contratação nem substitui a leitura dos requisitos da vaga.

### Importação de currículo
- Envio de currículo em PDF ou DOCX, com limite de 5 MB.
- Extração de informações para sugerir preenchimento de formação, experiências, cursos, certificações e projetos.
- Análise inteligente com Gemini quando a variável `GEMINI_API_KEY` está configurada.
- Extrator básico como alternativa quando a chave não está configurada.
- Revisão dos dados extraídos antes de salvar o perfil.

**Privacidade e controle:** o arquivo original não é salvo pelo endpoint de importação. A extração não sobrescreve o perfil automaticamente; a pessoa usuária revisa os campos e decide quando salvar. A análise com Gemini envia o texto extraído ao serviço do Google, portanto configure a chave e avalie as políticas do provedor antes de utilizar currículos com dados pessoais.

Endpoint: `POST /api/profile/import`.

### Acompanhamento de candidaturas
- Marcação de vagas favoritas.
- Registro de candidaturas.
- Pipeline para acompanhar as etapas dos processos seletivos.
- Registro de datas, informações de recrutadores e anotações.
- Indicadores de acompanhamento, incluindo vagas, candidaturas, entrevistas e novas oportunidades.

### Agente de candidaturas
Fluxo: **buscar → normalizar → eliminar duplicatas → filtrar estágio/júnior de tecnologia → avaliar compatibilidade → preparar → (aprovar) → enviar → registrar o resultado real**.

- Página **Agente**: ativar/desativar envio automático, exigir aprovação antes de cada envio, limite diário e compatibilidade mínima.
- **Duplicatas**: por URL normalizada e por título + empresa entre fontes diferentes.
- **Filtro**: considera vagas de estágio ou júnior classificadas como tecnologia pelo título.
- **Histórico**: tentativas registradas em `application_attempts`, com estados como `prepared`, `awaiting_approval`, `manual_required`, `sent`, `failed` ou `cancelled`.
- **Integridade**: uma candidatura só é marcada como enviada quando o servidor SMTP aceita a mensagem ou quando a própria pessoa confirma o envio manual.
- **Envio automático**: disponível somente por e-mail quando a descrição da vaga contém um endereço de contato e o SMTP está configurado. Nas demais situações, o agente prepara o texto e orienta a finalização no site original.
- **Conteúdo**: o texto utiliza somente informações cadastradas no perfil. O sistema não deve inventar experiências ou competências.
- Execução agendada opcional: `python -m jobfinder.agent_runner`.

### Fontes de vagas

| Fonte | Coleta | Candidatura automática |
|---|---|---|
| Remotive | API pública | Não (site original) |
| Arbeitnow | API pública | Não (site original) |
| OkEmprego | API | Não (site original) |
| Nerdin | Leitura da página pública (pode mudar se o layout mudar) | Não (site original) |
| Indeed | Sem integração de coleta; são apresentados links de busca | Não |
| Vagas.com | Sem integração de coleta; são apresentados links de busca | Não |

Para Indeed e Vagas.com, utilize os links de busca e adicione oportunidades manualmente. Nenhuma proteção, CAPTCHA ou login é contornado. A coleta real depende da disponibilidade e das condições de cada fonte; os testes automatizados não comprovam o funcionamento contínuo dos sites externos.

### Inteligência de mercado
A área **Inteligência de mercado** analisa competências encontradas nas oportunidades de estágio e nível júnior em tecnologia e permite comparar esses dados com o perfil profissional.

- Filtros por estágio, júnior ou ambos e janela de 30, 60 ou 90 dias.
- Ranking de linguagens, frameworks, bancos de dados, ferramentas e outras competências reconhecidas pela taxonomia inicial.
- Frequência de competências em vagas distintas e combinações que aparecem juntas.
- Indicadores de qualidade da amostra, incluindo quantidade de vagas e descrições aproveitáveis.
- Histórico de análises e botão para atualizar a análise.
- Avisos quando a amostra é pequena e explicação de que os percentuais de competências não somam necessariamente 100%, pois uma vaga pode mencionar várias tecnologias.

**Como interpretar os dados:** a análise usa a data `created_at` do banco, que representa quando a vaga foi observada pela primeira vez localmente, e não necessariamente sua data original de publicação. A extração inicial é determinística, baseada em nomes e aliases conhecidos. Ausência de uma competência na descrição não significa que ela não seja exigida. Frequência observada não é, isoladamente, uma recomendação definitiva de estudo.

### Skill Gap — mercado × perfil
- Cruza competências observadas nas vagas com formação, experiências, projetos, cursos, certificações e informações declaradas no perfil.
- Diferencia evidências profissionais, prática em projetos, cursos, certificações, formação, itens em estudo e competências não identificadas.
- Exibe recomendações para investigar ou desenvolver competências relevantes.

**Importante:** uma competência não identificada no currículo não é considerada automaticamente desconhecida. Menção em curso, projeto ou certificação também não comprova domínio técnico.

### Plano de desenvolvimento
- Adição de competências do Skill Gap a um plano individual.
- Registro de atividades sugeridas, estimativa de horas, prazo e anotações.
- Acompanhamento de status: planejada, em andamento, pausada ou concluída.
- Atualização de progresso e histórico das metas.

As atividades iniciais são sugestões genéricas por categoria de competência. O sistema ainda não é uma plataforma de cursos e não promete trilhas didáticas completas ou links de formação verificados.

### Desafios práticos e autoavaliação
- Geração de desafios conforme a categoria da competência.
- Registro da descrição da solução e de link opcional para repositório ou demonstração.
- Checklist de critérios e pontuação baseada nas respostas da própria pessoa.
- Histórico de tentativas e atualização do Skill Gap após o envio.

**Limitação atual:** os desafios não executam código, não inspecionam repositórios ou links e não verificam automaticamente a qualidade técnica da solução. A pontuação é uma autoavaliação, não uma certificação nem validação independente.

### Organização de tarefas
- Criação de tarefas relacionadas à busca de emprego.
- Definição de prazos e prioridades.
- Edição, conclusão e exclusão de tarefas.
- Opção de lembretes por e-mail, mediante configuração SMTP.

## Próxima evolução: avaliação objetiva de código

A arquitetura para uma futura avaliação automatizada de exercícios de Python, JavaScript e SQL está documentada em [docs/SECURE_CODE_ASSESSMENT.md](docs/SECURE_CODE_ASSESSMENT.md).

A proposta prevê testes definidos no servidor e execução em ambiente descartável, isolado e sem acesso à rede, com limites de recursos. **Essa funcionalidade ainda não está implementada.** Código enviado por usuários não será executado dentro do processo principal da API nem em ambiente que tenha acesso ao banco de dados, credenciais ou arquivos da aplicação. Se o runner seguro não estiver disponível, a avaliação deverá permanecer desabilitada.

## Tecnologias utilizadas

| Tecnologia | Aplicação |
|---|---|
| React | Interface de usuário |
| Vite | Ambiente de desenvolvimento do frontend |
| JavaScript | Lógica do frontend |
| Python | Lógica de negócio e integração com fontes |
| FastAPI | API REST |
| SQLAlchemy | Mapeamento objeto-relacional |
| SQLite | Persistência local |
| Gemini | Análise inteligente opcional do currículo |
| HTML5 e CSS3 | Estrutura e estilização da interface |
| Pytest | Testes automatizados |
| Git e GitHub | Versionamento e hospedagem do código |

## Arquitetura do projeto

A aplicação é organizada em duas partes principais:

- **Frontend:** interface React, responsável pela interação com o usuário, filtros, indicadores, perfil e acompanhamento das oportunidades.
- **Backend:** API FastAPI, responsável pela lógica de negócio, persistência, cálculo de compatibilidade, importação de currículo, inteligência de mercado e coleta de vagas.
- **Banco de dados:** SQLite na configuração local, com modelos SQLAlchemy.

A versão atual não oferece autenticação multiusuário. A interface utiliza a API local em `http://127.0.0.1:8000/api`; uma implantação pública exige configurar URLs por ambiente, banco de dados apropriado, autenticação, autorização e controles adicionais de segurança.

## Requisitos

- Python 3.11 ou superior.
- Node.js LTS e npm.
- Git.
- VS Code ou outro editor de código.
- Terminal compatível com os comandos do sistema operacional.

## Como executar o projeto

### 1. Clonar o repositório

```bash
git clone https://github.com/Stefany-viveiros/JobFinderAI.git
cd JobFinderAI
```

### 2. Preparar o backend

No terminal, na pasta raiz do projeto, crie o ambiente virtual:

```bash
py -3.11 -m venv .venv
```

Ative o ambiente virtual no Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instale as dependências:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Inicie a API:

```bash
python -m uvicorn jobfinder.api:app --reload
```

O backend ficará disponível em:

`http://127.0.0.1:8000`

A documentação interativa da API poderá ser acessada em:

`http://127.0.0.1:8000/docs`

### 3. Preparar o frontend

Abra um segundo terminal na pasta raiz e execute:

```bash
cd frontend
npm install
npm run dev
```

Abra no navegador o endereço apresentado pelo Vite, normalmente:

`http://localhost:5173`

Mantenha os dois terminais abertos enquanto estiver utilizando a aplicação.

## Configuração de ambiente

1. Copie `.env.example` para `.env`.
2. Para análise inteligente de currículo, configure `GEMINI_API_KEY`. Sem essa chave, a importação utiliza o extrator básico.
3. Para lembretes e envio de candidaturas por e-mail, configure as variáveis SMTP.
4. Nunca publique o arquivo `.env`, senhas ou chaves de API no GitHub.

A variável `JOBFINDER_DB_PATH` permite indicar outro caminho para o banco SQLite. Consulte o arquivo [.env.example](.env.example) para ver as opções disponíveis.

## Banco de dados e dados pessoais

O projeto utiliza SQLite na execução local. O banco é criado conforme a configuração do backend e utiliza o caminho definido na implementação.

Ao iniciar, a API cria as tabelas necessárias. O diretório `data/` pode conter informações pessoais, portanto esses arquivos não devem ser publicados no repositório. Faça cópias de segurança antes de qualquer migração ou alteração de ambiente.

## Configuração de e-mail

Os lembretes por e-mail e o envio de candidaturas por e-mail dependem das configurações de um servidor SMTP.

1. Copie `.env.example` para `.env`.
2. Preencha as variáveis com as credenciais fornecidas pelo seu provedor.
3. Teste o envio antes de configurar qualquer agendamento.

Use uma senha de aplicativo quando o provedor oferecer esse recurso. Nunca publique credenciais no GitHub.

Os scripts de agendamento existentes estão em `scripts/instalar_agendador.ps1`.

## Testes e integração contínua

Com o ambiente virtual ativado, execute na raiz do projeto:

```bash
pip install -r requirements-dev.txt
pytest -q
```

Os testes usam banco temporário e serviços simulados; não comprovam a coleta contínua em sites reais nem enviam e-mails reais.

O GitHub Actions executa duas verificações em pushes para `main` e branches `feature/**`, além de pull requests para `main`:

- **Backend tests:** instala dependências e executa `pytest -q`.
- **Frontend production build:** instala dependências com `npm ci` e executa `npm run build`.

## Documentação adicional

- [Inteligência de mercado, Skill Gap, plano e autoavaliação](docs/MARKET_INTELLIGENCE.md)
- [Arquitetura proposta para avaliação segura de código](docs/SECURE_CODE_ASSESSMENT.md)

## Estrutura de diretórios

```text
JobFinderAI/
├── jobfinder/
│   ├── api.py
│   ├── app.py
│   ├── models.py
│   ├── db.py
│   ├── matching.py
│   ├── service.py
│   ├── sources.py
│   ├── filters.py
│   ├── applying.py
│   ├── agent.py
│   ├── agent_runner.py
│   ├── market.py
│   ├── market_service.py
│   ├── resume_parser.py
│   └── resume_ai.py
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── MarketIntelligencePage.jsx
│       └── styles.css
├── docs/
│   ├── MARKET_INTELLIGENCE.md
│   └── SECURE_CODE_ASSESSMENT.md
├── scripts/
├── tests/
├── data/
├── .env.example
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

O arquivo `jobfinder/app.py` mantém a interface Streamlit anterior como referência. Para executar a versão React, utilize a API `jobfinder.api:app` e o frontend com Vite.

## Limitações conhecidas

- A aplicação ainda é destinada à execução local; não há deployment público nem autenticação multiusuário nesta versão.
- O envio automático de candidaturas só ocorre por e-mail quando há contato publicado na vaga e SMTP configurado.
- A coleta depende de serviços externos e mudanças nos sites podem interromper fontes que leem páginas públicas.
- A pontuação de compatibilidade é heurística e não prevê contratação.
- A inteligência de mercado depende das vagas coletadas, da qualidade das descrições e da taxonomia determinística inicial.
- A ausência de uma competência no texto da vaga ou no currículo não prova que ela não seja exigida ou conhecida.
- Desafios atuais são autoavaliações; ainda não há execução automatizada e isolada de código.
- Uma implantação pública exige autenticação, autorização, proteção de dados, configuração de serviços e revisão de segurança.

## Próximos passos

- Evoluir a classificação de competências e a qualidade das análises de mercado.
- Melhorar a experiência de importação e revisão do currículo.
- Implementar avaliação objetiva de exercícios somente após disponibilizar infraestrutura de execução isolada e segura.
- Preparar a arquitetura para implantação web, com frontend e backend acessíveis remotamente, persistência adequada e autenticação.
- Evoluir as fontes de vagas e a confiabilidade do agente de candidaturas.

## Autoria

Desenvolvido por **Stefany Viveiros** como projeto de portfólio para demonstrar conhecimentos em desenvolvimento web, APIs, Python, persistência de dados, análise de informações e automação de processos.

- GitHub: https://github.com/Stefany-viveiros
- Repositório: https://github.com/Stefany-viveiros/JobFinderAI
