# Cross-ecosystem security invariants

Security applies across the complete ecosystem: core, data, memory, risk, identity, SaaS, broker integration, execution, health monitoring, and audit.

- REAL execution remains disabled by default and is separate from production authorization.
- Health, alerts, market context, news, memory, statistics, and connectivity never authorize trades.
- Failures and unknown states fail closed.
- Protected production operations require trusted identity and tenant context.
- Local/in-memory persistence is never treated as durable tenant-scoped production storage.
- Tenant-boundary failures must be visible through ecosystem health.
- Market-context reasoning is observational only and cannot emit COMPRA, VENDA, AGUARDAR, score, entry, confidence, risk, or execution decisions.
- Unknown or unsafe component states are CRITICAL.
- A CRITICAL health state never grants execution authority.

These rules are maintained as executable regression tests so future features cannot silently weaken the safety boundary.
