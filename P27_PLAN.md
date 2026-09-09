# P27 — Execution Intent Admission

## Objetivo
Fazer a ponte segura entre `ExecutionIntent` e o `ExecutionGateway`, mantendo a intenção como contrato de entrada e impedindo que uma intenção inválida ou já processada alcance o executor.

## Regras
- somente `ExecutionIntent` validada pode ser admitida;
- a admissão deve preservar `request_id`, símbolo, sinal, valor, duração e modo;
- `REAL` continua bloqueado;
- `AGUARDAR` continua impossível como intenção;
- a camada não chama broker diretamente; usa apenas o gateway existente;
- nenhuma intenção é executada duas vezes pelo mesmo fluxo;
- falhas permanecem fail-closed.

## Critério de encerramento
Existe um caminho explícito `ExecutionIntent -> ExecutionGateway`, com validação e testes de rejeição, sem acoplamento a corretora ou rede.
