# Stage 4 — Reliability, Recovery & Multi-instance

Stage 4 trabalha em paralelo com a Stage 2 e não fecha nem substitui seus gates.

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
- recuperação de incidente exige condição verificável e não apenas reinício.

## Evidência obrigatória

Cada gate deve possuir teste executável, incluindo pelo menos um cenário de falha e um cenário de restart. A etapa não é considerada concluída por documentação isolada.
