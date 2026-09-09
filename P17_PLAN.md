# P17 — Runtime recovery foundation

## Objective
Create a durable, broker-agnostic runtime checkpoint that records the last safely completed cycle and supports restart recovery without inventing execution outcomes.

## Safety
- checkpoint is informational/recovery state only;
- invalid persisted state fails closed;
- no automatic order replay;
- REAL execution remains blocked;
- no strategy changes.
