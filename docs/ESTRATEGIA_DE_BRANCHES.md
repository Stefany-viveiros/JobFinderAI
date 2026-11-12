# Estratégia de branches — JobFinder AI

Atualizado em 12/11/2026.

## Branch de trabalho

- Branch ativa de implementação: `feature/proof-to-opportunity-engine`.
- Branch de referência para releases: `main`.
- Alterações novas devem entrar primeiro na branch ativa, com commits pequenos e CI verde.
- Não desenvolver diretamente em `main`.
- Não apagar branches históricas apenas por já terem sido mescladas; preservar rastreabilidade até a auditoria de histórico estar concluída.

## Situação verificada nesta rodada

- CI da branch ativa no commit `b603a76d52de020dfc5e608c6433178bb93300f3`: backend SQLite aprovado, backend PostgreSQL 16 aprovado e build de produção do frontend aprovado.
- A branch ativa contém as implementações recentes de cofre SMTP individual e migração `20261112_0005`, além do armazenamento cifrado de currículo.
- A comparação GitHub entre `main` e `feature/proof-to-opportunity-engine` reportou divergência: branch ativa 273 commits à frente e 5 atrás (a contagem inclui histórico de merges; não deve ser interpretada como 273 funcionalidades novas).
- Os commits recentes na linha principal incluem a adição e posterior reversão dos arquivos `alembic/versions/20261112_0005_smtp_accounts.py` e `jobfinder/smtp_credentials.py`. Esses arquivos existem na branch ativa e não foram encontrados em `main` na leitura feita em 12/11/2026.
- Portanto, não fazer merge automático, rebase forçado, reset ou exclusão de branches. A divergência precisa de revisão de diff e resolução consciente antes de abrir/atualizar uma PR de release.

## Regras para consolidação

1. Manter `feature/proof-to-opportunity-engine` como única branch de desenvolvimento ativa para esta rodada.
2. Branches de PR já mescladas são históricas; não mesclar novamente o mesmo trabalho.
3. Antes de propor PR para `main`, revisar a sequência de commits exclusivos de cada lado e os arquivos revertidos na linha principal.
4. Não restaurar arquivos revertidos em `main` sem entender a razão do revert e revisar o impacto nas migrações e no fluxo de credenciais.
5. Exigir CI verde após qualquer sincronização.
6. Merge em `main`, migração no banco de destino e deploy exigem aprovação explícita.

## Limites de release

CI verde valida os testes automatizados e o build, não comprova funcionamento de staging, Render, Neon, SMTP real, coleta ao vivo de todos os provedores ou execução segura de desafios. Seguir `docs/RELEASE_CHECKLIST.md`; manter os gates de produção fechados até validação operacional.
