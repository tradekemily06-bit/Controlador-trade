# P18 — Durable execution lifecycle

## Objective
Add a persistent execution lifecycle so an accepted execution cannot be confused with a durable request-ID record after a crash.

## States
PENDING, ACCEPTED, REJECTED, UNKNOWN.

## Safety
- uncertain execution is never automatically replayed;
- reconciliation is explicit and fail-closed;
- REAL execution remains blocked;
- no strategy changes.
