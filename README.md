# JobFinder AI — React + Python

Aplicação local para descoberta e acompanhamento de oportunidades de entrada em tecnologia. A interface foi migrada de Streamlit para **React + Vite** e o backend passou a oferecer uma **API REST com FastAPI**. O banco permanece em **SQLite**, com os modelos e a lógica de compatibilidade do projeto original.

## O que esta versão inclui

- Dashboard com indicadores de vagas, novas oportunidades, favoritos, candidaturas, entrevistas e tarefas.
- Busca sob demanda nas APIs públicas de Remotive e Arbeitnow, com indicação de falhas por fonte.
- Cadastro manual de vagas, pesquisa textual, filtros de compatibilidade/modalidade/favoritos e ordenação.
- Pontuação explicável de compatibilidade (0–100), com critérios encontrados e pontos a verificar.
- Favoritos e registro de candidaturas.
- Pipeline de candidaturas com etapa, datas, recrutador e notas.
- Tarefas com prazo, prioridade, edição, conclusão, exclusão e lembrete opcional.
- Edição do perfil profissional e recálculo das pontuações.
- Mantém os módulos de SMTP e agendamento diário já existentes; envio de e-mail depende de configuração no `.env`.
- Documentação interativa da API em `http://127.0.0.1:8000/docs`.

## Requisitos

- Python 3.11 ou superior.
- Node.js LTS com npm.
- Windows/PowerShell ou terminal compatível.

## Iniciar no Windows / VS Code

Abra a pasta `jobfinder-ai` no VS Code. Use **dois terminais**.

### 1. Preparar e iniciar o backend (Python)

No primeiro terminal, na pasta raiz `jobfinder-ai`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se você já tem o ambiente `.venv` configurado, não precisa recriá-lo: ative-o e rode `pip install -r requirements.txt` para incluir FastAPI/Uvicorn.

Depois, ainda nesse terminal:

```powershell
python -m uvicorn jobfinder.api:app --reload
```

Deixe esse terminal aberto. O backend será servido em `http://127.0.0.1:8000`.

### 2. Instalar e iniciar o frontend (React)

Abra **outro terminal** e execute:

```powershell
cd frontend
npm install
npm run dev
```

Abra o endereço mostrado pelo Vite, normalmente `http://localhost:5173`.

> Se `npm` não for reconhecido, instale a versão LTS do Node.js e reinicie o VS Code.

## Banco de dados e migração dos seus dados

O backend usa o mesmo caminho do projeto original: `data/jobfinder.db`. O arquivo é criado automaticamente na primeira execução.

**Importante ao substituir sua pasta atual:** o ZIP enviado não contém o seu banco SQLite pessoal (ele não estava incluído no ZIP original). Antes de trocar a pasta, faça uma cópia de `data\jobfinder.db`, se esse arquivo existir. Para manter seus dados, copie o arquivo do projeto anterior para `data\jobfinder.db` na nova pasta. Não compartilhe esse arquivo se ele contiver informações pessoais.

O arquivo `jobfinder/app.py` foi preservado como referência da interface Streamlit anterior; para usar React, inicie `jobfinder.api:app` e o frontend com Vite, conforme os passos acima.

## Perfil, compatibilidade e limitações

- A compatibilidade é uma heurística local explicável, não uma previsão de contratação.
- Remotive e Arbeitnow são fontes globais e não garantem cobertura de vagas de estágio no Brasil. Sempre confira os requisitos e a página original da vaga.
- O aplicativo permanece local e não oferece autenticação multiusuário. Não o publique na internet sem implementar autenticação, autorização e controles de segurança adicionais.
- A lista é carregada em até 250 vagas por consulta na interface; é possível ajustar esse limite no frontend.

## Configurar lembretes por e-mail (opcional)

Copie `.env.example` para `.env` e preencha com dados fornecidos pelo seu provedor SMTP. Nunca compartilhe o arquivo `.env` nem o publique no GitHub.

```dotenv
SMTP_HOST=smtp.seu-provedor.com
SMTP_PORT=587
SMTP_USERNAME=seu_usuario
SMTP_PASSWORD=sua_senha_de_app
SMTP_FROM=seu_email@exemplo.com
SMTP_TO=destino@exemplo.com
SMTP_USE_TLS=true
TIMEZONE=America/Sao_Paulo
```

Os recursos de agendamento existentes também estão em `scripts/instalar_agendador.ps1`. Configure e teste o SMTP antes de agendar envios.

## Testes

Com o ambiente Python ativado:

```powershell
pytest -q
```

Os testes unitários existentes não fazem chamadas reais às APIs nem enviam e-mails.

## Estrutura

```text
jobfinder-ai/
├── jobfinder/
│   ├── api.py           # API FastAPI para o React
│   ├── app.py           # interface Streamlit anterior, mantida como referência
│   ├── models.py        # modelos SQLAlchemy
│   ├── db.py            # banco SQLite
│   ├── matching.py      # pontuação de compatibilidade
│   ├── service.py       # operações do domínio
│   ├── sources.py       # fontes públicas de vagas
│   └── mailer.py        # lembretes SMTP
├── frontend/
│   ├── src/App.jsx      # interface React
│   ├── src/styles.css   # estilos responsivos
│   └── package.json
├── scripts/
├── tests/
├── data/                # banco local (não versionar)
├── .env.example
└── requirements.txt
```
