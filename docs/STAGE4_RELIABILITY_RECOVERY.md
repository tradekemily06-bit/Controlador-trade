# Stage 4 — Reliability, Recovery & Multi-instance

Stage 4 transforma restart, persistência, concorrência e recuperação em gates executáveis, sem enfraquecer as barreiras das etapas anteriores e sem habilitar REAL.

## Gates executáveis

- restart durante cada estado operacional relevante;
- estado ausente, truncado, corrompido e schema desconhecido → fail-closed;
- concorrência cross-process no ledger, safety store e incident store;
- duas instâncias nunca podem aceitar a mesma execução;
- UNKNOWN permanece UNKNOWN até evidência autorizada;
- reconciliação após restart não pode duplicar ação;
- locks são adquiridos antes das checagens finais sujeitas a TOCTOU;
- adapter/broker identity permanece igual antes e depois da execução;
- health/readiness não autoriza execução;
- recuperação de incidente exige condição verificável e não apenas reinício;
- divergência entre checkpoint, lifecycle e ledger bloqueia retomada automática;
- falha de persistência não pode ser convertida silenciosamente em estado seguro.

## Evidência obrigatória

Cada gate deve possuir teste executável, incluindo pelo menos um cenário de falha e um cenário de restart. A etapa não é considerada concluída por documentação isolada.

## Regra de segurança

A recuperação nunca cria uma nova submissão para uma operação cuja execução possa ter ocorrido. Estados `RESERVED` e `UNKNOWN` permanecem bloqueados até reconciliação autorizada com evidência suficiente. Nenhum health check, UI, API, configuração ou mecanismo de restart pode criar autoridade de execução.
