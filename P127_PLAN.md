# P127 — Adaptador DEMO cTrader

## Objetivo
Criar a primeira fronteira concreta de execução para uma conta DEMO cTrader, sem acoplar o núcleo do Controlador Trading ao broker e sem abrir qualquer caminho para REAL.

## Escopo
- aceitar somente `ExecutionMode.DEMO`;
- converter `ExecutionRequest` em `BrokerOrderRequest` através do contrato P123;
- delegar transporte externo por uma porta injetável, sem rede no núcleo;
- preservar `external_id` e resultado da corretora para reconciliação P121;
- rejeitar `AGUARDAR`, modo REAL e resultados inválidos de forma fail-closed;
- manter endpoint DEMO explícito (`demo.ctraderapi.com:5035` para Protobuf);
- não armazenar credenciais, tokens ou secrets no código.

## Fora do escopo
A implementação real do transporte cTrader/Open API depende da aprovação da aplicação e da autenticação OAuth. P127 não conecta sozinho à conta e não habilita REAL.

## Observação
O campo `duration_seconds` permanece no contrato comum do Controlador. Para cTrader/CFD, ele não deve ser interpretado automaticamente como expiração de ordem; essa semântica será definida por uma camada específica de execução quando necessário.
