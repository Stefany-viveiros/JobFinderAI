# Deploy do JobFinder AI na Oracle Cloud Infrastructure

**Estado:** infraestrutura Docker preparada em branch de trabalho; ainda não publicada na OCI.

Este guia prepara uma instalação econômica com uma VM Linux Always Free, Docker Compose, Caddy, React/Vite e FastAPI. O banco Neon existente é mantido inicialmente para evitar migração de dados e consumo de memória na VM.

## Arquitetura

- Caddy: proxy reverso, HTTPS automático e terminação TLS.
- Frontend: build Vite servido por Nginx.
- Backend: FastAPI em container Python 3.12, executado sem usuário root.
- Banco: Neon PostgreSQL existente, conectado por TLS.
- Volumes: dados locais opcionais e certificados/configuração persistentes do Caddy.

As portas 80 e 443 são publicadas. A porta 8000 da API e a porta 80 do frontend não são expostas diretamente à internet.

## Segurança por padrão

O arquivo `.env.oci.example` inicia com:

- `MULTITENANT_READY=false`: a área autenticada permanece bloqueada até a validação do isolamento.
- `DEMO_READ_ONLY=true`: mutações da API ficam bloqueadas até a aprovação do ambiente.
- `COOKIE_SECURE=true` e `APP_ENV=production`.

Não altere esses valores apenas para fazer a tela parecer funcional. A liberação exige backup, validação das migrações, preflight de staging e testes de isolamento multiusuário.

## Preparação da VM

1. Criar uma instância Ubuntu elegível ao Always Free na região desejada, confirmando disponibilidade e limites no painel Oracle antes de provisionar.
2. Reservar/confirmar o IPv4 público e configurar regras de entrada TCP 22, 80 e 443. Não abrir 8000 nem 5432.
3. Criar usuário administrativo sem login SSH por senha, instalar chave pública e restringir SSH à rede de administração sempre que possível.
4. Atualizar o Ubuntu e instalar Docker Engine e o plugin Docker Compose pelos repositórios oficiais.
5. Configurar o firewall do sistema para permitir somente SSH administrativo, HTTP e HTTPS.
6. Clonar este repositório e selecionar a branch/release aprovada. Não usar uma branch experimental como produção.

## DNS gratuito

Escolher um provedor de subdomínio gratuito confiável (por exemplo, DuckDNS) e criar um registro A apontando para o IPv4 público da VM. A propagação DNS deve estar concluída antes de iniciar Caddy.

O domínio precisa ser controlado pela proprietária. Não colocar tokens de DNS no repositório.

## Configuração do ambiente

No servidor:

```bash
cp .env.oci.example .env
chmod 600 .env
nano .env
```

Preencher pelo menos `DOMAIN` e `DATABASE_URL` com valores obtidos diretamente nos respectivos painéis. Não enviar senhas ou chaves por chat.

Gerar duas chaves Fernet diferentes, uma para currículos e outra para credenciais SMTP:

```bash
docker compose run --rm --no-deps api python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Guardar a chave de currículo e a chave SMTP em local seguro e inserir em `.env`. A perda da chave de currículo impede recuperar os arquivos cifrados.

## Verificação antes de iniciar

- Confirmar que `DATABASE_URL` aponta para a instância Neon correta e que o TLS está habilitado.
- Criar backup verificável do banco de staging/cópia de teste.
- Executar `scripts/preflight_release.py` contra staging, nunca contra produção como primeiro teste.
- Revisar o estado Alembic e os registros sem proprietário.
- A API OCI usa `AUTO_INIT_DB=false`: não executa `create_all()` nem alterações DDL na inicialização. Aplicar Alembic será uma etapa explícita, revisada e precedida por backup.

## Build e inicialização

Depois de aprovada a release:

```bash
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=100 api web caddy
```

Caddy solicita e renova certificados automaticamente quando DNS e portas estão corretos.

Verificar:

```bash
curl -fsS https://SEU_DOMINIO/api/health
curl -fsS https://SEU_DOMINIO/api/health/ready
```

O endpoint de prontidão pode informar bloqueio enquanto o gate multiusuário estiver fechado. Isso é intencional.

## Liberação do produto

Somente após staging validado, backup restaurável, testes de isolamento e auditoria de endpoints:

1. Configurar `MULTITENANT_READY=true`.
2. Configurar `DEMO_READ_ONLY=false`.
3. Reiniciar a API: `docker compose up -d --force-recreate api`.
4. Testar cadastro, login, logout, recuperação de senha, importação e isolamento com duas contas de teste.
5. Testar a persistência após reiniciar os containers.
6. Confirmar HTTPS e cookies Secure no navegador.

Não habilitar o envio SMTP até configurar chaves, conta SMTP e currículo individual cifrado. Começar por um endereço de teste controlado.

## Atualização e rollback da aplicação

Antes de cada atualização:

```bash
docker compose ps
docker compose logs --tail=200 api
```

Manter a última release aprovada identificada por tag Git. Para voltar ao código anterior, selecionar a tag anterior e reconstruir:

```bash
git checkout TAG_ANTERIOR
docker compose build
docker compose up -d
```

Rollback de código não reverte automaticamente o schema do banco. Nunca executar downgrade destrutivo. Restaurar backup somente com procedimento revisado e após confirmar o ponto de recuperação.

## Backup

O banco Neon deve ter backup/exportação conforme o plano e as ferramentas disponíveis. Validar restauração em banco separado. Guardar também cópia segura das chaves Fernet, fora da VM e fora do Git.

Os volumes `caddy_data` e `caddy_config` contêm estado de TLS/configuração e devem ser preservados. O volume `jobfinder_data` existe para dados locais opcionais; não substitui backup do PostgreSQL.

## Custos e limites

A arquitetura foi desenhada para caber nos recursos Always Free, mas a elegibilidade depende da conta, região, disponibilidade de capacidade, configuração e políticas Oracle vigentes. Conferir cada SKU e estimativa no console antes de criar. Não habilitar recursos pagos, IPs/serviços fora da franquia ou upgrades sem autorização expressa.

## Pendências para concluir o deploy

- [ ] Aprovar e integrar esta branch após CI.
- [ ] Confirmar elegibilidade/capacidade Always Free na região escolhida.
- [ ] Criar a VM Ubuntu e registrar IP público.
- [ ] Configurar subdomínio DNS gratuito.
- [ ] Configurar SSH, firewall e Docker.
- [ ] Preparar cópia de staging e validar Alembic/preflight.
- [ ] Corrigir qualquer bloqueio do schema antes de liberar multiusuário.
- [ ] Inserir segredos diretamente no servidor.
- [ ] Publicar e validar HTTPS, frontend, API e persistência.
- [ ] Testar reinício, backup e restauração.
- [ ] Configurar Gemini e SMTP por último.
