# Stage 6 — Product, UX, Learning & SaaS boundaries

Stage 6 consolidates the ecosystem experience without mixing product surfaces with financial authorization.

## Gates

- Operation, Analysis, Memory, Laboratory/Replay and Learning have separated responsibilities;
- onboarding explains the system without changing operational state;
- important notifications are prioritized without flooding the operational surface;
- local preferences can never authorize execution;
- learning memory cannot change the Risk Gate or execution identity;
- API and UI cannot construct REAL privileges;
- persistent user state is isolated by trusted tenant/subject scope where applicable;
- UI and learning failures cannot bypass execution barriers;
- mobile-first behavior remains usable;
- critical security information remains visible and legible.

## Rule

UX may facilitate an already-authorized action; it can never create authorization. Learning and laboratory surfaces remain separate from operation and safe for hypothetical or replay scenarios.

## Validation boundary

Stage 6 is considered incomplete until the product-boundary tests pass together with the full repository suite on the current Stage 5 base. A failure in an unrelated prerequisite contract is treated as a blocking dependency, not hidden by narrowing the Stage 6 test scope.
