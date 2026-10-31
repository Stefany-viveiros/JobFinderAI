# Avaliação técnica objetiva de competências — arquitetura segura

## Objetivo

Evoluir os desafios atuais de autoavaliação para exercícios executáveis com testes definidos pelo servidor. A execução deve ser complementar à autoavaliação e nunca transformar, por si só, um resultado isolado em certificação ou garantia de proficiência.

## Decisão de segurança

**Código enviado pela pessoa usuária nunca será executado dentro do processo FastAPI, do worker principal ou do mesmo ambiente que contém o banco de dados e os segredos da aplicação.**

A execução só poderá acontecer em um runner isolado, descartável e sem acesso à rede. Se o ambiente de sandbox não estiver disponível, a API deve falhar de forma fechada: informar que a avaliação automática está temporariamente indisponível, sem tentar executar o código localmente.

## Escopo inicial

A primeira versão objetiva será limitada a três linguagens:

- Python
- JavaScript (Node.js)
- SQL (SQLite em banco efêmero)

Outras competências continuam usando o fluxo atual de desafio e autoavaliação até receberem uma suíte de testes própria.

## Contrato dos exercícios

Cada exercício executável deve ter uma definição versionada mantida no servidor:

- identificador estável e versão;
- competência e linguagem compatíveis;
- enunciado e assinatura/contrato esperado;
- arquivos de entrada permitidos;
- testes públicos de exemplo;
- testes privados definidos pelo servidor;
- limites de tempo, memória e tamanho;
- critérios objetivos de aprovação.

Não aceitar testes, comandos, imagem Docker, argumentos de execução ou caminhos de arquivo enviados pela pessoa usuária. O cliente envia somente o código-fonte e o identificador de um exercício permitido. O servidor escolhe a imagem, o comando, os testes e os limites.

### Exercícios iniciais sugeridos

- Python: implementar uma função pura de transformação/validação de dados, testada com casos normais, limites e entradas inválidas.
- JavaScript: implementar a mesma família de função com contrato equivalente, executada em Node.js.
- SQL: escrever uma consulta sobre um conjunto de tabelas SQLite efêmero e retornar linhas esperadas; não aceitar comandos de administração do host nem acesso a arquivos externos.

Os enunciados e testes precisam ser específicos e coerentes. Não tentar avaliar automaticamente o desafio genérico atual de mini projeto com uma rubrica que não corresponde a um contrato executável.

## Isolamento obrigatório do runner

A implementação com Docker deverá:

- usar imagens oficiais versionadas e fixadas por digest antes de produção;
- executar um container descartável por submissão;
- desabilitar rede (network none);
- executar como usuário não privilegiado;
- remover todas as capabilities e ativar no-new-privileges;
- usar filesystem raiz somente leitura;
- montar somente o diretório temporário da submissão, sem permissão de escrita;
- fornecer apenas diretórios temporários limitados via tmpfs;
- impor limites de CPU, memória, processos, tamanho de arquivos e tempo;
- não montar o socket do Docker, diretórios do host, banco de dados, credenciais ou variáveis de ambiente da aplicação;
- encerrar o container em timeout e remover os arquivos temporários;
- limitar e sanitizar stdout/stderr antes de persistir ou devolver ao cliente.

O runner deve receber somente identificadores e conteúdo validado. Nunca concatenar código ou entrada do usuário em comandos de shell; usar argumentos separados e arquivos temporários controlados.

## Persistência e resultado

O resultado objetivo deve ser armazenado separadamente do registro de autoavaliação, preservando:

- exercício e versão;
- linguagem;
- hash do código submetido;
- quantidade de testes aprovados e total;
- status técnico (passed, failed, timeout, runner_unavailable, error);
- duração e timestamp;
- feedback seguro e limitado.

Não persistir imagens, containers ou arquivos executáveis após a execução. Não armazenar o código-fonte por padrão; se futuramente houver opção de histórico de código, ela deverá ser explícita e documentada.

## Interpretação dos resultados

- Testes aprovados demonstram que a solução passou nos casos definidos, não que a pessoa domina toda a tecnologia.
- Testes reprovados devem mostrar feedback útil sem revelar os testes privados completos.
- Timeout, erro de infraestrutura e runner indisponível não podem ser apresentados como reprovação técnica.
- O Skill Gap deve distinguir evidência de perfil, autoavaliação e teste automatizado.
- Não criar status validada ou proficiente com base em um único exercício.

## Integração com o produto

Fluxo previsto:

1. Pessoa seleciona uma competência elegível.
2. API apresenta um exercício versionado.
3. Pessoa envia o código-fonte.
4. API valida tamanho, linguagem e exercício.
5. Runner isolado executa a suíte privada.
6. API registra o resultado técnico e atualiza o histórico.
7. Skill Gap mostra separadamente o resultado automatizado e a autoavaliação.

## Dependências de infraestrutura

A execução objetiva depende de um ambiente de deployment que suporte um runner isolado com containers e limites de recursos. Não é suficiente hospedar apenas FastAPI e React em uma plataforma sem suporte a containers de execução.

Antes de habilitar a funcionalidade em produção, será necessário definir:
- serviço/host do runner;
- política de imagens e atualização de imagens;
- autenticação interna entre API e runner;
- fila e limite de concorrência;
- observabilidade, rate limit e proteção contra abuso.

## Critérios de aceite

- Código arbitrário nunca roda no processo FastAPI.
- Nenhum segredo ou dado do usuário fica acessível ao container.
- Rede desabilitada e limites de recursos são aplicados.
- Timeout e indisponibilidade são estados distintos de reprovação.
- Testes privados são definidos no servidor.
- Testes unitários cobrem validação de payload, seleção de exercício, falhas do runner e persistência.
- O CI valida o contrato do runner sem executar código arbitrário fora de sandbox.
- A funcionalidade permanece desabilitada quando o runner seguro não estiver configurado.
