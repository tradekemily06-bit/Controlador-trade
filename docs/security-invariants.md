# Cross-ecosystem security invariants

These invariants apply to the entire Controlador-trade ecosystem, not only the SaaS or broker layer.

## Execution safety

- REAL execution is disabled by default.
- Health status, alerts, market context, news, memory, statistics, or connectivity must never authorize an operation.
- Production authorization is separate from trading execution authorization.
- A failure or unknown state must fail closed rather than silently becoming permissive.

## Isolation and identity

- Protected production operations require trusted identity and tenant context.
- Local or in-memory persistence must not be treated as durable tenant-scoped production storage.
- Tenant-boundary failures must be visible to ecosystem health monitoring.

## Reasoning boundaries

- Market-context reasoning is observational and explanatory only.
- It must not emit COMPRA, VENDA, AGUARDAR, score, entry, confidence, risk, or execution decisions.
- Operational decisions remain behind the decision and risk gates.

## Health monitoring

- Known healthy states remain non-alerting.
- Expected but incomplete configuration is visible as WARNING where appropriate.
- Unknown or unsafe component states are CRITICAL.
- A CRITICAL health state never grants execution authority; it only increases protection and visibility.

## Regression protection

Security invariants are tested as executable contracts so future features cannot accidentally weaken the safety boundary.
