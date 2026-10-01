# Execução

A camada de execução é broker-agnostic e permanece separada da decisão e do risco.

## Caminho atual

- O núcleo permanece broker-agnostic.
- **IC Markets MT5 DEMO** é a integração DEMO concreta usada pelo runtime operacional atual, mas não é um padrão implícito do aplicativo.
- O provider é selecionado explicitamente na borda de integração por `CONTROLADOR_EXECUTION_PROVIDER`.
- O registro DEMO atual é criado por `execution.default_registry.build_demo_registry()`.
- A criação do registro é local e não inicializa o MT5 nem envia ordens.
- A disponibilidade do terminal/conta só deve ser verificada no ponto de execução ou em um preflight explícito.
- **REAL permanece desabilitado**.
- **cTrader é futuro e não bloqueia o desenvolvimento atual**.

## Segurança

Nenhum adapter pode contornar o `ExecutionGateway`, o `DemoReadiness`, o kill switch, a proteção contra duplicidade ou as validações de modo DEMO.
