# Interface Information Architecture Contract

This contract defines where ecosystem capabilities belong so the mobile interface stays operationally clear without hiding controls that can change whether an operation is allowed.

## Visibility rule

A capability is **primary** when it can directly change, block, authorize, or invalidate an operation. Primary capabilities must remain reachable from the operational cockpit without traversing an administrative area.

Secondary capabilities may use progressive disclosure. This is intentional: the interface should expose the primary workflow first and defer advanced/rarely used material instead of putting every feature on the first screen.

## Visual composition rule

The final product interface must **not use a dashboard made of repeated grids of cards/boxes as the primary visual language**. The goal is a clean, chart-first operational interface.

- Charts/market visualization are the dominant visual elements where a chart materially communicates information.
- Keep only controls and status elements that are necessary for operating, understanding, or safely blocking the system.
- Avoid decorative card grids, metric-box mosaics, nested boxes, and repeated bordered panels that make the screen look like a collection of tiles.
- Do not create a chart merely to replace every piece of text; use concise text for status, explanation, alerts, and controls when that is clearer.
- Statistics should prefer meaningful charts (trend, distribution, comparison) over rows of metric cards.
- Operational decision, risk, environment, execution, reconciliation, and critical alerts may use compact status treatments when necessary, but they should not become a wall of cards.
- The chart area must remain readable on mobile and should be prioritized over secondary decoration.
- Progressive disclosure should reduce visual density without hiding safety-critical state.

## Layer 1 — Operational cockpit

Keep immediately reachable:

- current asset/market and chart context;
- COMPRA / VENDA / AGUARDAR decision;
- decision quality/strength and confirmation state;
- current operational state;
- risk gate and active blocking reason;
- DEMO/REAL environment state;
- execution and reconciliation state;
- critical alerts;
- kill switch / emergency control.

A critical failure must surface here even when its normal home is elsewhere.

## Layer 2 — Analysis and immediate context

Keep one step away or compactly attached to the cockpit:

- analysis inputs and result explanation;
- filters and confirmation factors;
- market/context observations that can affect the current decision;
- relevant news/context status;
- currently relevant technical concepts and discoveries.

The technical concept list is knowledge already structured by the ecosystem, not a whitelist limiting future discovery.

## Layer 3 — Dedicated study and review areas

Do not compete with the operational cockpit:

- laboratory and replay;
- visual training/material analysis;
- learning activities;
- operational memory and feedback;
- statistics and historical breakdowns;
- discovery exploration;
- expanded knowledge/reference content.

Newly discovered relationships remain distinguishable from validated rules and must never silently acquire execution authority.

## Layer 4 — Administration and technical diagnostics

Keep available but out of the operational flow:

- local settings;
- connections;
- detailed security/tenant administration;
- component health and diagnostics;
- technical/audit detail;
- maintenance information.

Administrative detail must not replace the operational safety state shown in Layer 1.

## Non-negotiable separation

- Learning is informational and never authorizes trading.
- Discovery is exploratory and never becomes a trading rule without validation.
- Replay/lab does not imply live execution.
- News/context is evidence/context, not an automatic signal.
- REAL remains architecturally blocked until the required validation gate is satisfied.
- Risk, environment, execution, reconciliation, and critical security failures cannot be hidden behind deep navigation.
- Adding a feature must not automatically create another top-level navigation item.

## Acceptance criteria

The interface is considered correctly organized only when:

1. the operational path is the shortest path for decisions and safety;
2. secondary information is progressively disclosed instead of competing with the cockpit;
3. study/review functions are visibly separate from execution authority;
4. technical/admin detail is separated from user-facing operation;
5. critical conditions can surface to the cockpit regardless of their normal section;
6. mobile navigation does not require a long row of unrelated top-level destinations;
7. the information architecture does not remove any existing safe API capability merely to make the UI cleaner;
8. the primary visual language is chart-first rather than a repeated grid of dashboard cards;
9. only necessary controls/status surfaces use compact containers;
10. charts remain legible and useful on mobile.
