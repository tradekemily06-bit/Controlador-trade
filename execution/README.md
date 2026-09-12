# Execução

A camada de execução é broker-agnostic e permanece separada da decisão e do risco.

## Caminho atual

- **IC Markets MT5 DEMO** é o adapter concreto padrão.
- O registro padrão é criado por `execution.default_registry.build_demo_registry()`.
- A criação do registro é local e não inicializa o MT5 nem envia ordens.
- A disponibilidade do terminal/conta só deve ser verificada no ponto de execução ou em um preflight explícito.
- **REAL permanece desabilitado**.
- **cTrader é futuro e não bloqueia o desenvolvimento atual**.

## Segurança

Nenhum adapter pode contornar o `ExecutionGateway`, o `DemoReadiness`, o kill switch, a proteção contra duplicidade ou as validações de modo DEMO.
