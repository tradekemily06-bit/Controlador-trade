# P61 — Avaliação de proposta de adaptação

## Objetivo
Criar uma fronteira explícita para avaliar uma proposta P60 antes de qualquer aplicação, mantendo a decisão separada da proposta original.

## Regras
- consumir somente proposta P60 válida;
- resultado deve ser explicitamente fornecido: APPROVED, REJECTED ou NEEDS_REVIEW;
- não aplicar a proposta;
- não alterar estratégia, score, risco ou execução;
- preservar a proveniência P60;
- imutável, determinístico e fail-closed.

## Critério de encerramento
Toda proposta de adaptação passa por uma avaliação explícita antes de poder avançar para uma eventual aplicação controlada.
