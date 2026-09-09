# P11 — Operational Analytics

P11 formalizes analytics over the validated operational memory without changing strategy or execution behavior.

Scope:
- derive immutable analytics snapshots from `OperationMemory`;
- filter metrics by inclusive timestamp period;
- report WIN/LOSS/AMBOS/PENDENTE counts and win rate;
- report performance by COMPRA/VENDA and quality level;
- report decision distribution for EXECUTAR/BLOQUEAR/AGUARDAR;
- preserve the underlying memory unchanged.

Validation criteria:
- invalid periods are rejected;
- empty memory produces safe zero/`None` metrics;
- period boundaries are inclusive;
- direction and quality metrics exclude unresolved/ambiguous outcomes from win-rate denominators;
- analytics never mutate operation memory;
- full test suite and project compilation pass in CI.

P11 does not create a new strategy, execute orders, connect brokers, or enable REAL execution.
