## Multi-account adapter sessions (runtime foundation)

The standalone runtime now has a tenant-and-subject-scoped adapter-session registry. It binds each verified broker connection ID to one distinct server-side read-only adapter instance. Multiple accounts at the same provider and accounts at different providers can coexist without sharing adapter objects. A binding is rejected unless the connection metadata belongs to the caller, is currently CONNECTED, and the internal caller confirms a successful adapter handshake. Browser-supplied status is not accepted.

The session registry is process-local: adapter instances are intentionally not persisted or exposed to clients. After a process restart, every provider must reconnect and complete a new handshake before analysis can use it. This is an adapter-isolation foundation, not yet a complete multi-provider feed fan-out: per-connection candle ingestion, independent timeframe workers, per-account analysis endpoints, encrypted credential/OAuth lifecycle, and live broker end-to-end tests remain pending. No order execution or money movement is added.


The connection status view also reports a bounded adapter health snapshot. Only approved non-secret fields are exposed (connected, account_mode, last_seen, source_id, stored_candles). A bound adapter is not automatically considered live: it is CONNECTED only when its heartbeat is recent (30 seconds, with a small clock tolerance); otherwise it is stale, disconnected, unverified or in status error.
