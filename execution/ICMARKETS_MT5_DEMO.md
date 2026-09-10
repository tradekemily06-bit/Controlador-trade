# IC Markets — MT5 DEMO

O Controlador Trading agora possui uma boundary de execução para **IC Markets via MetaTrader 5 (DEMO)**.

## Arquitetura

`decision core → risk/gateway → BrokerAdapter → IC Markets MT5 DEMO → terminal MT5`

O núcleo de decisão não depende do MT5. O adapter pode ser substituído por outra integração sem reescrever score, filtros, risco, auditoria ou gateway.

## Runtime

A integração usa o pacote oficial `MetaTrader5` da MetaQuotes e comunica-se com um terminal MT5 em execução. Por isso, `MetaTrader5` fica em `requirements-mt5.txt`, separado da suíte normal do projeto. O runtime operacional deve ser Windows com o terminal MT5 instalado e conectado.

## Segurança atual

- somente `ExecutionMode.DEMO` é aceito;
- a conta precisa ser identificada pelo terminal como conta DEMO;
- `AGUARDAR` nunca gera ordem;
- `order_check()` é executado antes de `order_send()`;
- nenhuma credencial é gravada no repositório;
- o adapter não contém lógica de sinal, score ou gestão de risco;
- `duration_seconds` não é convertido em expiração, porque MT5 trabalha com posições/ordens e não com expiração binária. O fechamento deve ser tratado pelo ciclo de execução apropriado.

## Limite importante

Esta etapa cria e testa a **boundary de software**. Ela não comprova uma conexão real com a conta IC Markets até o runtime Windows/MT5 ser executado com uma conta DEMO válida.

O cTrader permanece preservado como adapter futuro, mas não é mais uma dependência para continuar o projeto.
