# P17 — Runtime recovery foundation

Durable runtime checkpointing for safe restart and recovery.

## Scope
- immutable checkpoint with session and last processed cycle/request;
- JSON persistence and restoration;
- fail-closed validation of corrupted state;
- no automatic re-execution of an uncertain cycle.