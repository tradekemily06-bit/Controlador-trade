# P58 — Auditoria antes da memória analítica

## Objetivo
Impedir que a memória analítica aceite conhecimento sem proveniência e validação suficientes.

## Regras
- consumir somente registro P57 válido;
- verificar identidade, origem e consistência antes da admissão;
- produzir uma decisão factual AUDITABLE ou BLOCKED;
- não corrigir automaticamente dados inconsistentes;
- não alterar estratégia, score, risco ou execução;
- imutável, determinístico e fail-closed.

## Critério de encerramento
A memória analítica possui uma barreira de auditoria explícita antes da admissão de conhecimento.
