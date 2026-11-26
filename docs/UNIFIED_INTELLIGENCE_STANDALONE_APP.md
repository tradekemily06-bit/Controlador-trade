# Unified intelligence and standalone application boundary

## Target architecture

The product has seven user-facing areas, all routed through one shared intelligence coordinator:

1. Cabine de Comando
2. Análise
3. Estudo
4. Memória
5. Reserva Fiscal
6. Assistente do Ecossistema
7. Central

The 45+ senior experience baseline, specialist domains, financial-market curriculum, reasoning, memory, research, risk, audit and security are internal capabilities. They are not additional navigation areas.

## Safety and truthfulness

- The application is an analyst and information system; this layer never submits broker orders.
- Every route and area contract has execution_authorized=false.
- Learning, research and discoveries do not become operational rules without evidence and validation.
- Missing area handlers are reported as NOT_CONNECTED; no integration is fabricated.
- AGI/ASI is a research ambition, not a verified property or marketing claim.
- A shared intelligence coordinator does not by itself provide a foundation model, live market feed, persistent multi-tenant storage or push delivery.

## Implementation status of this first slice

This change adds the shared intelligence contract, the seven-area registry, the read-only application facade and tests. It does not claim that all seven functional services, providers, authentication, fiscal data sources, live feeds, mobile push or deployment have been connected. Those require individual adapters, credentials/configuration where applicable, integration tests and production validation.

The approved Lovable interface is outside this change and must remain visually unchanged.
