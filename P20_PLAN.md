# P20 — Production readiness foundation

## Objective
Create a broker-agnostic readiness boundary before any future real execution.

## Scope
- explicit environment/readiness states;
- fail-closed production gate;
- REAL execution remains disabled;
- verify that safety dependencies are present before readiness can be reported;
- no strategy changes and no direct broker calls;
- tests and CI validation.
