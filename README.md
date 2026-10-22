# JobFinder AI

**Plataforma inteligente para busca, análise de compatibilidade e acompanhamento de oportunidades na área de tecnologia.**

O JobFinder AI é um projeto desenvolvido para facilitar a organização da busca por oportunidades de estágio e posições júnior em tecnologia. A aplicação reúne funcionalidades para consultar vagas, avaliar a compatibilidade com um perfil profissional, organizar candidaturas e acompanhar as etapas de processos seletivos.

O projeto evoluiu de uma interface construída com Streamlit para uma arquitetura com **React + Vite no frontend** e **FastAPI no backend**, mantendo Python para a lógica de negócio e SQLite para persistência local dos dados.

## Funcionalidades

### Busca e organização de vagas
- Coleta de oportunidades por meio das fontes de vagas implementadas no backend.
- Indicação de falhas durante a consulta às fontes.
- Cadastro manual de oportunidades.
- Pesquisa textual, filtros por compatibilidade, modalidade e favoritos.
- Ordenação e visualização das oportunidades disponíveis.

### Análise de compatibilidade
- Pontuação de compatibilidade entre o perfil profissional e os requisitos identificados na vaga.
- Escala de compatibilidade de 0 a 100.
- Exibição dos critérios encontrados e dos pontos que precisam ser verificados.
- Possibilidade de atualizar o perfil profissional e recalcular as pontuações.

### Acompanhamento de candidaturas
- Marcação de vagas favoritas.
- Registro de candidaturas.
- Pipeline para acompanhar as etapas dos processos seletivos.
- Registro de datas, informações de recrutadores e anotações.
- Indicadores de acompanhamento, incluindo vagas, candidaturas, entrevistas e novas oportunidades.

### Organização de tarefas
- Criação de tarefas relacionadas à busca de emprego.
- Definição de prazos e prioridades.
- Edição, conclusão e exclusão de tarefas.
- Opção de lembretes por e-mail, mediante configuração SMTP.

### API e persistência de dados
- API REST desenvolvida com FastAPI.
- Persistência local com SQLite e modelos SQLAlchemy.
- Documentação interativa dos endpoints.
- Testes automatizados para funcionalidades do projeto.

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
| HTML5 e CSS3 | Estrutura e estilização da interface |
| Pytest | Testes automatizados |
| Git e GitHub | Versionamento e hospedagem do código |

## Arquitetura do projeto

A aplicação é organizada em duas partes principais:

- **Frontend:** interface React, responsável pela interação com o usuário, filtros, indicadores e acompanhamento das oportunidades.
- **Backend:** API FastAPI, responsável pela lógica de negócio, persistência, cálculo de compatibilidade e coleta das vagas.

O banco SQLite é utilizado para armazenar os dados localmente. A aplicação não oferece, nesta versão, autenticação multiusuário.

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

## Banco de dados

O projeto utiliza SQLite para persistência local. O banco é criado conforme a configuração do backend e utiliza o caminho definido na implementação.

O diretório `data/` pode conter arquivos locais com informações pessoais. Esses arquivos não devem ser publicados no repositório. Para preservar dados existentes ao trocar de ambiente, faça uma cópia de segurança antes de qualquer migração.

## Configuração de e-mail

Os lembretes por e-mail dependem das configurações de um servidor SMTP.

1. Copie o arquivo `.env.example` para `.env`.
2. Preencha as variáveis com as credenciais fornecidas pelo seu provedor.
3. Teste o envio antes de configurar qualquer agendamento.

Nunca publique o arquivo `.env`, senhas ou chaves de API no GitHub.

Os scripts de agendamento existentes estão em `scripts/instalar_agendador.ps1`.

## Testes

Com o ambiente virtual ativado, execute na raiz do projeto:

```bash
pytest -q
```

Os testes automatizados existentes verificam funcionalidades do projeto sem depender de chamadas reais às APIs externas ou do envio efetivo de e-mails.

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
│   └── mailer.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── styles.css
│   └── package.json
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

- A pontuação de compatibilidade é uma heurística explicável e não representa uma previsão de contratação.
- A disponibilidade e a qualidade dos resultados dependem das fontes integradas e de seus dados.
- As informações da vaga devem ser conferidas na página original antes de uma candidatura.
- O sistema é destinado ao uso local e não possui autenticação multiusuário.
- Uma implantação pública exige controles adicionais de autenticação, autorização, proteção de dados e segurança.

## Próximos passos

O projeto pode evoluir com melhorias na cobertura das fontes de vagas, refinamento dos filtros, aprimoramento da experiência visual e novas ferramentas para apoiar a organização da busca por oportunidades.

## Autoria

Desenvolvido por **Stefany Viveiros** como projeto de portfólio para demonstrar conhecimentos em desenvolvimento web, APIs, Python, persistência de dados e automação de processos.

- GitHub: https://github.com/Stefany-viveiros
- Repositório: https://github.com/Stefany-viveiros/JobFinderAI
