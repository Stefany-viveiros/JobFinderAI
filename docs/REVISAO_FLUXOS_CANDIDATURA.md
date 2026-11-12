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

**Estado de validação:** alterações commitadas na branch ativa; execução de CI após estes commits ainda precisa ser confirmada. Não declarar release validado antes de SQLite, PostgreSQL 16 e build Vite ficarem verdes.

## Limitações ainda presentes

- O envio por e-mail é um canal limitado a anúncios que publicam um endereço contextual de recrutamento; não é integração universal com portais.
- Endereço extraído da descrição não substitui confirmação humana da legitimidade do recrutador. A configuração recomendada continua exigindo aprovação antes do envio.
- Não há integração automática de candidatura em portais que exigem login, CAPTCHA, APIs privadas ou fluxos não autorizados.
- Testes de CI não substituem teste SMTP real com conta de teste, staging e validação dos segredos persistentes.
- O modo multiusuário permanece fechado até a auditoria operacional e validação do banco de destino.
