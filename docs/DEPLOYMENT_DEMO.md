# Publicar a demonstração do JobFinder AI

Esta configuração cria um frontend estático e uma API no Render, usando um banco PostgreSQL hospedado no Neon. A configuração não publica o banco local nem importa o currículo ou os dados existentes no notebook.

## 1. Criar o banco no Neon

1. Entre em https://neon.tech/ e crie um projeto PostgreSQL novo, exclusivo para a demonstração.
2. Abra **Connect** no painel do projeto.
3. Selecione a branch e o banco criados para a demonstração.
4. Ative **Connection pooling** e copie a connection string PostgreSQL.
5. Guarde essa URL. Ela contém a senha do banco: não a coloque no GitHub, em arquivos do projeto ou em mensagens.

O código lê a URL pela variável `DATABASE_URL` e usa SSL conforme os parâmetros fornecidos pelo Neon.

## 2. Criar os serviços no Render

1. Entre em https://render.com/ e conecte sua conta GitHub.
2. No painel do Render, escolha **New → Blueprint**.
3. Selecione o repositório `Stefany-viveiros/JobFinderAI` e a branch `main`.
4. O Render deve identificar o arquivo `render.yaml` e apresentar dois serviços: `jobfinder-ai-api` e `jobfinder-ai-web`.
5. Quando solicitado, informe a connection string do Neon somente no campo secreto `DATABASE_URL` do Render.
6. Revise os recursos e confirme a criação.

Os endereços configurados são:
- Frontend: https://jobfinder-ai-web.onrender.com
- API: https://jobfinder-ai-api.onrender.com
- Verificação da API: https://jobfinder-ai-api.onrender.com/api/health

Se o Render gerar nomes diferentes por conflito de nomes, ajuste `VITE_API_URL` no serviço frontend e `CORS_ORIGINS` no serviço da API para os domínios efetivamente exibidos no painel. Depois faça novo deploy dos dois serviços.

## 3. Proteções desta demonstração

- `DEMO_READ_ONLY=true`: a API bloqueia POST, PUT, PATCH e DELETE.
- Use um banco Neon novo, vazio e exclusivo para esta demonstração.
- Não configure SMTP, envio de candidaturas ou credenciais pessoais.
- Não envie seu currículo real nem cadastre dados pessoais.
- A demonstração ainda não tem autenticação multiusuário. Os endpoints GET são públicos; portanto, somente dados fictícios ou não sensíveis podem existir nesse banco.
- Não altere `DEMO_READ_ONLY` para `false` antes de implementar e testar autenticação e autorização por usuário.

## 4. O que validar

1. Abra o frontend e confira se o painel carrega sem erro de conexão.
2. Acesse a URL `/api/health` da API e confirme `{"status":"ok"}`.
3. Confira a tipografia, os cartões, filtros, menus e comportamento em notebook e celular.
4. Ações que alteram dados devem responder com HTTP 403 nesta versão de demonstração; isso é intencional.

## 5. Custos e disponibilidade

Consulte os planos e limites atuais diretamente nos painéis do Render e do Neon antes de confirmar a criação. Serviços gratuitos podem ter limites de uso, suspensão por inatividade ou condições que mudam com o tempo.