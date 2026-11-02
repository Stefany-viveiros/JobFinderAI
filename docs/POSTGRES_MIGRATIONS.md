# Migrações de banco — JobFinder AI

O schema do banco deve ser atualizado com Alembic. O `init_db()` permanece responsável pela inicialização/compatibilidade histórica da aplicação, mas não substitui migrações versionadas.

## Antes de migrar produção

1. Faça um backup/snapshot do banco Neon.
2. Confirme que `DATABASE_URL` aponta para o banco correto.
3. Execute `alembic current` para verificar a revisão registrada.
4. Execute `alembic upgrade head`.
5. Execute os testes de integridade e só então habilite `MULTITENANT_READY=true`.

## Comandos

```bash
pip install -r requirements.txt -r requirements-dev.txt
alembic current
alembic history
alembic upgrade head
```

Para conferir a revisão instalada:

```bash
alembic current
```

## Revisão 20261102_0001

A revisão remove a restrição global UNIQUE em `applications.job_id` e garante UNIQUE composto em `(user_id, job_id)`. Ela:

- preserva as linhas existentes;
- interrompe a migração se encontrar candidaturas duplicadas para o mesmo usuário e vaga;
- não atribui registros legados sem proprietário a uma conta arbitrária;
- recusa downgrade se a nova estrutura já permitir candidaturas da mesma vaga em contas diferentes, pois restaurar a unicidade global exigiria excluir dados.

A revisão é compatível com PostgreSQL e SQLite. Em SQLite, usa reconstrução transacional da tabela via Alembic batch mode.

**Importante:** esta migração resolve a constraint de candidaturas. Ela não substitui a auditoria de isolamento das demais tabelas nem autoriza, por si só, a ativação do SaaS em produção.
