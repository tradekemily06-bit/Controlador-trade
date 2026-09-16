# Stage 3 — Deployment and State Authority Gate

## Purpose

This document defines the minimum deployment topology required before the ecosystem is treated as production-ready. It does not enable REAL execution.

## Single-instance DEMO

A single process may use the local persistent runtime state already composed by `build_operational_runtime()`. The runtime owns the operational ledger, lifecycle, safety state, incident state, checkpoint and recovery components.

## Public multi-instance deployment

A public multi-instance deployment must not rely on independent local safety files. If authoritative shared state is not configured, startup must fail closed rather than silently running multiple isolated safety domains.

The required future topology is:

`application instances -> shared authoritative state service -> execution/runtime barriers`

Each instance must observe the same authoritative execution state, kill switch, incident state, replay ledger and recovery state. Local caches may be informational, but they cannot become execution authority.

## Startup and recovery rules

1. Missing/corrupt critical state blocks execution.
2. Recovery never converts `UNKNOWN` into a fresh submission.
3. A restart must preserve request identity and replay protection.
4. Health/observability cannot grant execution authority.
5. Secrets must not be persisted in operational state files.
6. REAL remains separately disabled until an independent release gate is satisfied.

## Broker integration boundary

The first production-integration target remains DEMO/sandbox broker connectivity. The broker adapter must enter through the existing gateway boundary and retain explicit adapter identity, market-data identity, external-order identity and reconciliation evidence.

## Exit evidence

Stage 3 Gate B is not considered passed from documentation alone. It requires executable tests against the actual deployment topology, including multi-instance shared-state behavior, restart, corruption/failure and recovery scenarios.
