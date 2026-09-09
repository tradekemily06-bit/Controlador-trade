# P43 — Admissão segura de ciclos automatizados

## Objetivo
Transformar um pedido de ciclo autorizado pelo P42 em uma admissão explícita para o ciclo DEMO, exigindo que as fronteiras operacionais existentes permaneçam saudáveis.

## Regras
- consumir somente `AutomationCycleRequest` válido do P42;
- exigir prontidão DEMO do P30;
- exigir orçamento operacional P40 aprovado para a operação proposta;
- não criar ordens, executar operações ou alterar estado operacional;
- REAL permanece bloqueado;
- falhas de tipo, prontidão ou orçamento devem bloquear (fail-closed);
- resultado imutável e determinístico;
- nenhuma chamada de rede, corretora, timer ou thread.

## Critério de encerramento
Existe uma fronteira testada que admite somente ciclos DEMO explicitamente autorizados pelo P42 e simultaneamente aprovados pela prontidão DEMO e pelo orçamento de risco, sem efeitos colaterais.
