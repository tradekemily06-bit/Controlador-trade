# Auditoria profunda — contrato de replay

## Objetivo

O replay é laboratório/análise. Ele nunca pode se transformar em autoridade de execução e não deve permitir que uma requisição parcialmente inválida produza histórico parcialmente gravado.

## Limites já existentes

- O corpo HTTP possui teto global de 256 KiB.
- `/api/replay` aceita no máximo 50 cenários por requisição.
- O serviço também aplica o mesmo teto de 50, evitando que um chamador interno contorne o limite HTTP.
- Cada cenário precisa ser um objeto.
- A resposta mantém `execution_allowed: false`.

O limite de 50 é uma barreira de quantidade, não um orçamento completo de recursos.

## Regra de pré-validação — IMPLEMENTADA

Antes de iniciar qualquer análise que persista memória/decisão, o fluxo agora:

1. consome no máximo 51 itens do iterável recebido;
2. rejeita quando existe o 51º item;
3. valida que todos os itens aceitos são objetos;
4. somente depois inicia as análises e gravações.

A mesma política é aplicada no serviço por `core.replay_policy.prevalidate_replay_cases()` e é coberta por testes para o 51º cenário e para um cenário inválido depois de cenários válidos.

Isso elimina o comportamento perigoso anterior: processar e persistir os primeiros cenários e somente depois descobrir que havia um cenário excedente ou um item inválido mais adiante.

A pré-validação é limitada a 51 itens e não materializa uma entrada arbitrariamente grande.

## Custo de processamento

A quantidade de cenários não é suficiente para representar custo computacional. O próximo endurecimento deve observar, conforme a implementação do replay evoluir:

- tamanho serializado de cada cenário;
- profundidade/complexidade estrutural da entrada;
- número de candles ou objetos derivados por cenário;
- tempo total de processamento;
- memória usada pelo laboratório;
- quantidade de registros gerados;
- cancelamento/aborto seguro;
- comportamento quando uma análise individual falhar.

Não devem ser introduzidos números arbitrários apenas para satisfazer uma auditoria. Cada teto adicional precisa corresponder a uma propriedade mensurável do runtime.

## Atomicidade do efeito de memória

A correção de pré-validação foi aplicada na fronteira do serviço. O replay ainda reutiliza `analyze()`, que grava cada `DecisionRecord` na memória e no `DecisionStore`, mas agora nenhuma gravação começa enquanto o envelope inteiro, dentro do limite de 50, não estiver validado.

Isso resolve a falha de validação tardia do envelope. Ainda permanece uma questão diferente: se uma análise individual falhar depois que outras já foram persistidas, a semântica de replay parcial precisa ser explicitamente definida ou tornada recuperável antes de considerar o contrato transacional completo.

## Multi-tenant

Em SaaS público, replay não pode reutilizar o `DecisionStore` global. Os registros produzidos precisam nascer com `subject_id` e `tenant_id` vindos da identidade confiável e ser persistidos em repositório tenant-scoped. A identidade não pode vir do payload do navegador.

## Critério de fechamento desta frente

A auditoria de replay somente será considerada fechada quando:

- o limite de quantidade existir no HTTP e no serviço — **resolvido**;
- a entrada for pré-validada antes de qualquer efeito persistente — **resolvido**;
- falha de cenário não produzir uma conclusão enganosa de replay completo — **pendente de semântica de falha individual**;
- o caminho SaaS estiver ligado a armazenamento tenant-scoped real — **pendente por configuração estrutural de produção**;
- não houver qualquer caminho do replay para autorização REAL — **mantido bloqueado e coberto pela arquitetura atual**.
