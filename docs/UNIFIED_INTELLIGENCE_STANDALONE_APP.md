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

## Existing service wiring

The standalone application factory now composes the current ecosystem service, senior contextual reasoning, learning/curriculum, operational memory, read-only fiscal summaries and the read-only assistant behind the same intelligence object. Fiscal owner identity is injected from trusted server configuration, never from a request.

Only services actually supplied to the factory are marked CONNECTED. The analysis area requires a validated market-context object from a market-data adapter. Fiscal and assistant areas remain NOT_CONNECTED until their persistent stores, trusted identity and provider are configured. No order or money movement is exposed.


## Broker-neutral market analysis

The standalone Analysis area can receive any provider implementing the existing MarketDataProvider contract. Its feed is normalized and validated, then passed through the existing strategy pipeline, signal-quality evaluator, market-context engine and the shared senior-context gate. It returns a candidate signal and evidence score only; it never submits orders. Stale, gapped, invalid or unsupported-timeframe data force AGUARDAR.

The 10-minute timeframe is now included alongside 1m, 5m, 15m, 30m, 1h, 4h and 1d. No broker provider is enabled by default: a provider must be injected and its freshness/quality checks must pass. A configured API model is separate from the market-data feed and does not make the system an AGI/ASI.
