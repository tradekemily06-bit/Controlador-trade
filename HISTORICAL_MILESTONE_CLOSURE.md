# Historical milestone closure — P2, P4 and P7

This document closes the historical PR-status discrepancy without merging obsolete PRs into `main`.

## P2
The old PR #1 was closed without merge. Its intended historical-validation boundary was not present in current `main`, so P2 is being incorporated cleanly in this branch with a dedicated implementation and tests. The old PR remains historical.

## P4
The old PR #3 was not merged, but its operational-recording responsibility is present in the current architecture through `P4OperationalRecorder`, `PersistentOperationalRecorder`, and gateway integration. P4 therefore does not need to be reimplemented or merged from the old PR. Its current-main implementation is the authoritative version.

## P7
The old PR #7 was not merged because it was contaminated by unrelated P4/P5/P6 work. The current `main` already contains the P7 market-data foundation and `P7_PLAN.md` records the scope as completed. P7 therefore does not need the old PR merged. The current-main implementation is authoritative.

## Closure rule
P2, P4 and P7 are tracked by current-main implementation and tests, not by whether obsolete historical PRs were merged. No historical PR is merged merely to change its status.
