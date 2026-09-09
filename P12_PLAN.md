# P12 — Operational Reporting and Observability

P12 adds a read-only reporting boundary over the validated operational analytics and memory layers.

Scope:
- combine an immutable analytics snapshot with the records used to produce it;
- support inclusive period filtering through the existing analytics contract;
- preserve chronological, validated memory without mutation;
- provide a stable report object for future dashboards, exports and monitoring;
- keep reporting separate from strategy, execution and broker adapters.

Validation criteria:
- reports are immutable;
- reported records match the selected period;
- analytics and records describe the same source window;
- generating a report never mutates OperationMemory;
- invalid dependencies are rejected;
- full test suite and compilation pass in CI.

P12 does not create a new trading strategy, execute orders, connect brokers, or release REAL execution.
