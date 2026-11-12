# Revisão dos fluxos operacionais — 12/11/2026

Branch analisada: `feature/proof-to-opportunity-engine`.

## Fluxo revisado

1. Coleta: conectores autorizados retornam anúncios; fontes link-only são rejeitadas no endpoint de coleta.
2. Normalização/deduplicação: URLs e chave título/empresa identificam duplicatas.
3. Elegibilidade: o agente seleciona apenas estágio/júnior de tecnologia.
4. Compatibilidade: pontuação e requisitos obrigatórios são recalculados por conta.
5. Preparação: currículo/carta usam somente dados presentes no perfil; a tentativa não é marcada como enviada.
6. Canal: envio por e-mail depende de endereço de candidatura publicado, SMTP individual e currículo cifrado por conta no modo multiusuário; sem isso, o fluxo exige finalização no portal.
7. Aprovação/envio: a API verifica compatibilidade e requisitos obrigatórios; a tentativa só vira enviada após aceite SMTP ou confirmação manual explícita.
8. Histórico: tentativas, candidaturas e eventos são consultados por conta.

## Problemas encontrados e correções aplicadas nesta rodada

- **Deduplicação podia colapsar URLs distintas:** a normalização anterior convertia o endereço inteiro para minúsculas. Isso podia fundir caminhos/valores de query que diferem por caixa em servidores sensíveis. Agora apenas esquema e host são normalizados; caminho e valores de parâmetros preservam caixa. Tracking conhecido é removido sem apagar parâmetros genéricos como `reference`.
- **Contato genérico podia ser escolhido para receber currículo:** a extração anterior aceitava qualquer e-mail não bloqueado na descrição. Agora exige contexto explícito próximo ao endereço (candidatura, currículo, seleção, recrutamento, RH, talentos, vagas, careers/jobs/apply etc.). Contato geral e suporte não são tratados como destino de candidatura.
- **Filtro de nível podia ser desativado pelo payload:** `POST /api/jobs/collect` aceitava `only_target=false`. Agora a rota força o escopo de estágio/júnior de tecnologia, alinhado ao produto.
- **Vaga cancelada não podia voltar à fila do agente:** a consulta de candidatas excluía qualquer tentativa anterior, inclusive canceladas. Agora tentativas canceladas deixam de bloquear uma nova preparação; enviadas e outras tentativas continuam bloqueando duplicidade.

## Testes adicionados/ajustados

- URLs com caminho e valores de query sensíveis a maiúsculas/minúsculas.
- Remoção de tracking sem colapsar parâmetros de negócio.
- Rejeição de endereços genéricos de contato/suporte como destino de candidatura.
- Payload tentando desativar o filtro estágio/júnior.
- Reprocessamento de vaga após cancelamento de tentativa.

**Estado de validação (12/11/2026):** CI do commit `2318c3fcf7301df23cde29eb8c9b258afe48c3f3` concluído com sucesso nos três jobs: backend SQLite, backend PostgreSQL 16 e build de produção Vite. Isso valida a suíte automatizada e a compilação, mas não equivale a homologação em staging nem a teste de entrega SMTP real.

## Limitações ainda presentes

- O envio por e-mail é um canal limitado a anúncios que publicam um endereço contextual de recrutamento; não é integração universal com portais.
- Endereço extraído da descrição não substitui confirmação humana da legitimidade do recrutador. A configuração recomendada continua exigindo aprovação antes do envio.
- Não há integração automática de candidatura em portais que exigem login, CAPTCHA, APIs privadas ou fluxos não autorizados.
- Testes de CI não substituem teste SMTP real com conta de teste, staging e validação dos segredos persistentes.
- O modo multiusuário permanece fechado até a auditoria operacional e validação do banco de destino.


## Auditoria de isolamento e currículo — 12/11/2026

Revisão estática da branch ativa:

- Sessões usam token aleatório no cookie HttpOnly; o banco armazena SHA-256 do token. Escritas exigem CSRF e sessões expiradas/inativas são recusadas.
- As rotas de currículo filtram por `request.state.user_id`; o arquivo é armazenado com Fernet, digest SHA-256 e nome saneado. O upload aceita apenas PDF/DOCX, limita o tamanho a 5 MB e aplica limite de cinco importações por hora por conta.
- A leitura e remoção do currículo são por proprietário. A suíte de API verifica que uma segunda conta não enxerga o currículo da primeira e que o anexo enviado por e-mail corresponde ao arquivo cifrado da conta autenticada.
- `validate_multitenant_schema()` exige FKs, proprietários não nulos, unicidade por usuário e consistência entre evidências/revisões e candidaturas/eventos. A aplicação mantém o gate fechado quando `MULTITENANT_READY` não está ativo.
- A cadeia Alembic revisada vai de `20261102_0001` até `20261112_0006`; a migração de currículo cria `user_resumes` com FK e unicidade por usuário.

## Bloqueios antes de liberar usuários reais

1. **Render ainda está em modo de demonstração:** o Blueprint define `DEMO_READ_ONLY=true` e `MULTITENANT_READY=false`. Isso é deliberado e impede considerar o serviço atual como SaaS pronto.
2. Aplicar e validar todas as migrações no banco de staging/destino, verificar `alembic current` e executar a validação multiusuário com dados legados sem atribuir registros a contas arbitrárias.
3. Configurar segredos persistentes independentes `RESUME_STORAGE_KEY` e `SMTP_CREDENTIALS_KEY`; confirmar backup/recuperação das chaves. Não girar nem perder a chave de currículo após armazenar arquivos.
4. Fazer teste ponta a ponta em staging com duas contas isoladas, upload e exclusão de currículo, preparação, aprovação e envio para uma caixa de teste.
5. Só então decidir, com autorização explícita, a alteração de `DEMO_READ_ONLY`, `MULTITENANT_READY`, migrações e deploy. A configuração Gmail da usuária permanece para a etapa final.

**Conclusão da auditoria:** a implementação tem proteções importantes e testes automatizados verdes, mas ainda não está pronta para liberar candidaturas reais nem para declarar o MVP publicado. Nenhuma migração ou configuração de produção foi executada nesta revisão.
