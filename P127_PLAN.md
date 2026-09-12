# P127 — Integração DEMO IC Markets MT5

## Objetivo
Tornar a integração IC Markets MT5 DEMO a primeira fronteira concreta de execução do Controlador Trading, mantendo o núcleo independente do broker e sem abrir qualquer caminho para REAL.

## Estado atual
O adapter `ICMarketsMT5DemoAdapter` já implementa a fronteira MT5 DEMO. O registro padrão agora expõe o broker como `ic_markets_mt5_demo`, sem inicializar o terminal durante a construção do registro e sem armazenar credenciais.

## Escopo
- aceitar somente `ExecutionMode.DEMO`;
- manter `ExecutionRequest` como contrato comum do ecossistema;
- registrar o adapter por uma camada explícita de broker, isolada do motor de decisão;
- preservar `external_id` e resultado do MT5 para reconciliação e auditoria;
- validar conta DEMO, símbolo, cotação e `order_check()` antes de `order_send()`;
- rejeitar `AGUARDAR`, modo REAL, volume inválido e resultados não confirmados de forma fail-closed;
- manter credenciais e secrets fora do código e do repositório.

## Fora do escopo
- execução REAL;
- alteração do motor de decisão ou do Risk Gate para favorecer o broker;
- conexão automática sem um terminal MT5 DEMO disponível;
- cTrader/Open API.

## Próxima expansão
O caminho cTrader/Open API permanece futuro e não bloqueante. O próximo trabalho de integração deve fortalecer o fluxo IC Markets MT5 DEMO — disponibilidade, execução controlada, reconciliação, auditoria e interface — antes de qualquer expansão para outro broker.

## Observação
`duration_seconds` continua sendo parte do contrato comum do Controlador. No adapter MT5, esse campo é metadado e não cria expiração automática de posição; o fechamento é uma operação separada e controlada.
