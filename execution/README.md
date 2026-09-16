# Execução

A camada de execução é broker-agnostic e permanece separada da decisão e do risco.

## Caminho atual

- **IC Markets MT5 DEMO** é o adapter concreto padrão.
- O registro padrão é criado apenas internamente por `execution.default_registry._build_demo_registry()` durante a composição do gateway.
- O registro não exporta mais um `get()` que entregue o adapter; ele expõe somente metadados. O lookup executável exige a capacidade privada da barreira de broker e ocorre apenas na composição interna.
- O chamador recebe o `ExecutionGateway`, não o adapter concreto.
- A criação do registro é local e não inicializa o MT5 nem envia ordens.
- A disponibilidade do terminal/conta só deve ser verificada no ponto de execução ou em um preflight explícito.
- `order_check()` e `order_send()` permanecem exclusivamente na fronteira do adapter de broker.
- **REAL permanece desabilitado**.
- **cTrader é futuro e não bloqueia o desenvolvimento atual**.

## Segurança

Nenhum adapter pode contornar o `ExecutionGateway`, o `BrokerAdapterGateway`, o kill switch, a proteção contra duplicidade, o ledger durável ou as validações de modo DEMO.

Recuperação/restart nunca reconstrói uma execução a partir de checkpoint. Estados `RESERVED`/`UNKNOWN`, divergências entre lifecycle e ledger e checkpoints órfãos bloqueiam a retomada automática e exigem reconciliação explícita.
