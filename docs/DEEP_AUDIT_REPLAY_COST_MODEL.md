# Auditoria profunda — contrato de replay

## Objetivo

O replay é laboratório/análise. Ele nunca pode se transformar em autoridade de execução e não deve permitir que uma requisição parcialmente inválida produza histórico parcialmente gravado.

## Regra arquitetural sobre capacidade

**O Replay não possui um limite funcional artificial de quantidade de cenários.** O antigo valor 50 foi removido do núcleo, do serviço e da API.

Capacidade e proteção são conceitos diferentes. O ecossistema pode ter proteções de transporte, memória, concorrência, armazenamento, tempo de execução e infraestrutura quando forem necessárias para preservar disponibilidade e segurança. Essas proteções não podem ser transformadas em um limite arbitrário de cenários, candles, operações ou capacidade funcional.

Qualquer proteção futura deve ser baseada no recurso real que está sendo protegido, ser mensurável e permitir continuidade por paginação, streaming, processamento assíncrono ou outra forma adequada quando o volume exceder a capacidade de uma resposta síncrona.

## Pré-validação

Antes de iniciar qualquer análise que persista memória/decisão, o fluxo valida o envelope recebido e rejeita itens que não sejam objetos. Não existe mais um sentinel de 51º cenário nem uma contagem máxima de cenários.

A pré-validação continua sendo importante para impedir que um erro estrutural tardio produza efeitos parciais.

## Atomicidade do efeito de memória — IMPLEMENTADA

O Replay agora executa as análises sem persistência individual. Os `DecisionRecord` são coletados em memória durante a fase de análise e somente depois enviados ao caminho de persistência em lote.

O `DecisionStore` possui `save_many()` e usa uma única transação SQLite para o lote. A memória do serviço também só é atualizada depois que a persistência do lote termina com sucesso.

Assim, uma falha durante a análise não deixa os cenários anteriores do mesmo Replay gravados. Uma falha no armazenamento também não atualiza a memória do serviço como se a gravação tivesse sido concluída.

## Custo de processamento

A quantidade de cenários não representa, por si só, o custo computacional. O contrato deve observar, conforme o Replay evoluir:

- tamanho real dos dados;
- profundidade/complexidade estrutural;
- número de candles e objetos derivados;
- CPU e tempo de processamento;
- memória residente;
- volume de registros produzidos;
- concorrência;
- cancelamento e recuperação;
- armazenamento disponível;
- comportamento individual de falhas.

Não devem ser introduzidos números arbitrários para satisfazer auditoria. Quando uma proteção de infraestrutura for necessária, ela deve proteger o recurso correspondente e não ser apresentada como limite funcional do ecossistema.

## Multi-tenant

Em SaaS público, Replay não pode reutilizar o `DecisionStore` global. Os registros produzidos precisam nascer com `subject_id` e `tenant_id` vindos da identidade confiável e ser persistidos em repositório tenant-scoped. A identidade não pode vir do payload do navegador.

## Segurança operacional

Replay continua sendo somente laboratório/análise. Toda resposta mantém `execution_allowed: false`, e nenhum resultado do Replay pode autorizar REAL.

## Critério de fechamento desta frente

- limite funcional artificial de cenários — **REMOVIDO**;
- pré-validação estrutural antes de efeitos persistentes — **RESOLVIDO**;
- falha durante análise não gera persistência parcial — **RESOLVIDO**;
- falha de armazenamento não apresenta memória como persistida — **RESOLVIDO**;
- caminho SaaS ligado a armazenamento tenant-scoped real — **pendente por configuração estrutural de produção**;
- caminho do Replay para autorização REAL — **inexistente/bloqueado pela arquitetura atual**.
