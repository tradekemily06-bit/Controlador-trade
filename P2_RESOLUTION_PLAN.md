# P2 — Historical validation resolution

## Objective
Incorporate the historical decision-validation boundary into the current `main` without merging the old contaminated PR.

## Scope
- chronological replay using only candles available at each decision point;
- explicit EXECUTAR/BLOQUEAR/AGUARDAR decisions;
- integration with the existing deterministic `BacktestEngine` for historical TP/SL outcomes;
- preservation of WIN/LOSS/AMBOS/PENDENTE outcomes;
- validation of candle chronology and decision inputs;
- automated coverage for look-ahead prevention and edge cases.

## Safety
- historical validation is offline/read-only with respect to live execution;
- no broker/network access;
- no REAL execution;
- no automatic strategy, risk, score, or knowledge mutation.

## Resolution criterion
P2 is considered resolved only when its clean implementation is present on `main` and its tests pass in CI. The old PR #1 remains historical and is not merged.
