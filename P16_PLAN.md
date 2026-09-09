# P16 — Idempotência durável da execução

## Objetivo

Tornar durável a proteção contra execução duplicada iniciada no P5, preservando request IDs processados após reinício.

## Escopo

- persistir request IDs processados pelo ExecutionGateway;
- restaurar esses IDs após reinício;
- rejeitar uma requisição já processada mesmo depois de recriar o gateway;
- manter o ledger independente de corretora e do modo de execução;
- preservar o kill switch, auditoria e memória já existentes;
- falhar fechado quando o ledger persistido estiver inválido;
- manter execução REAL bloqueada.

## Critérios de validação

1. Request IDs processados sobrevivem a um novo gateway.
2. Uma requisição restaurada é recusada como DUPLICATE.
3. IDs inválidos ou estado persistido inválido são rejeitados.
4. Uma execução aceita é persistida antes de ficar disponível para uma nova instância.
5. O gateway continua aceitando somente DEMO.
6. A suíte existente permanece verde.
