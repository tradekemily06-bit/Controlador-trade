# P31 — DEMO Execution Coordinator

## Objetivo
Criar a primeira fronteira de orquestração entre a prontidão DEMO, a intenção de execução e o `ExecutionGateway`, sem permitir execução REAL nem chamadas diretas a corretoras.

## Regras
- a prontidão P30 é verificada antes de qualquer chamada ao gateway;
- somente `ExecutionIntent` DEMO pode prosseguir;
- `AGUARDAR`, intenção inválida ou REAL permanecem bloqueados;
- quando não estiver READY, nenhum executor é chamado;
- o coordenador usa somente contratos existentes (`DemoReadiness`, `ExecutionIntent` e `ExecutionGateway`);
- nenhum replay automático é introduzido;
- o resultado preserva a decisão de prontidão e o resultado do gateway.

## Critério de encerramento
Existe um coordenador DEMO testado que liga P30 → intenção → gateway, mantendo a execução REAL bloqueada e falhando fechado em qualquer condição de prontidão inválida.
