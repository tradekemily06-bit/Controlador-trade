# REAL dispatch composition boundary

## Current verified state

The REAL gateway is a strict dispatch boundary, but the repository currently does not provide a production application-level constructor that wires it to concrete authoritative runtime sources. This is intentional fail-closed behavior: the gateway now requires both an authoritative `RiskStateProvider` and an authoritative `RealSafetyProvider`.

`RuntimeRealSafetyProvider` supplies the composition primitive. It reads six live boolean sources on every call:

- REAL authorization active
- kill switch clear
- market healthy
- recovery safe
- risk approved
- broker available

The provider does not cache a report and does not invent a safe default. A source failure propagates to the REAL gateway, which converts the failure into a sanitized UNKNOWN result without dispatch.

## Required production wiring before REAL enablement

A future production constructor must bind those six sources to the ecosystem's authoritative runtime components, not test doubles, request payloads, stale decision snapshots, or process-local convenience state. The same constructor must bind the authoritative risk-state provider used by the decision snapshot revalidation.

The production wiring must then prove:

1. kill switch reads the durable/shared operational safety source;
2. technical incidents are read from the durable/shared incident barrier;
3. maintenance is read from the authoritative maintenance source;
4. recovery is read from the authoritative recovery coordinator/state;
5. market health/identity comes from the authoritative market-data boundary;
6. broker availability is checked at the actual selected broker boundary;
7. risk approval is derived from the authoritative current risk state;
8. authorization/admission cannot be replaced by caller-supplied lookalike objects;
9. every REAL dispatch uses the same gateway and ledger path;
10. multi-instance deployments use shared authoritative state for every safety source.

Until that wiring and its integration tests exist, the presence of `RealExecutionGateway` must not be interpreted as enabling REAL trading.
