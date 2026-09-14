# Auditoria profunda — contrato de replay

## Objetivo

O replay é laboratório/análise. Ele nunca pode se transformar em autoridade de execução e não deve permitir que uma requisição parcialmente inválida produza histórico parcialmente gravado.

## Limites já existentes

- O corpo HTTP possui teto global de 256 KiB.
- `/api/replay` aceita no máximo 50 cenários por requisição.
- Cada cenário precisa ser um objeto.
- A resposta mantém `execution_allowed: false`.

O limite de 50 é uma barreira de quantidade, não um orçamento completo de recursos.

## Regra de pré-validação

Antes de iniciar qualquer análise que persista memória/decisão, o fluxo deve:

1. consumir no máximo 51 itens do iterável recebido;
2. rejeitar imediatamente quando existir o 51º item;
3. validar que todos os itens aceitos são objetos;
4. somente depois iniciar as análises e gravações.

Isso evita o seguinte comportamento perigoso: processar e persistir os primeiros 50 cenários e somente então descobrir que havia um 51º cenário ou um item inválido mais adiante.

A pré-validação deve ser limitada a 51 itens, e não deve materializar uma entrada arbitrariamente grande em memória.

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

O replay atual reutiliza `analyze()`, que grava cada `DecisionRecord` na memória e no `DecisionStore`. Portanto, a fronteira correta é:

`validar entrada -> executar replay -> persistir resultados`

ou, se a arquitetura mantiver persistência incremental:

`validar completamente a entrada -> executar/persistir com estado intermediário recuperável -> nunca tratar resultado parcial como replay concluído`.

Para o laboratório local atual, a pré-validação de todos os cenários (limitada a 51 itens) é a correção mínima mais segura.

## Multi-tenant

Em SaaS público, replay não pode reutilizar o `DecisionStore` global. Os registros produzidos precisam nascer com `subject_id` e `tenant_id` vindos da identidade confiável e ser persistidos em repositório tenant-scoped. A identidade não pode vir do payload do navegador.

## Critério de fechamento desta frente

A auditoria de replay somente será considerada fechada quando:

- o limite de quantidade existir no HTTP e no serviço;
- a entrada for pré-validada antes de qualquer efeito persistente;
- falha de cenário não produzir uma conclusão enganosa de replay completo;
- o caminho SaaS estiver ligado a armazenamento tenant-scoped real;
- não houver qualquer caminho do replay para autorização REAL.
