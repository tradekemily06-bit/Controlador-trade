# cTrader read-only market-data adapter

The repository now has a broker-neutral `CTraderReadOnlyMarketDataAdapter` that implements the standalone provider contract and normalizes cTrader trendbars into the shared `Candle` model.

## Supported DEMO periods

| App timeframe | cTrader Open API period |
| --- | --- |
| 1m | M1 |
| 5m | M5 |
| 10m | M10 |
| 15m | M15 |
| 30m | M30 |
| 1h | H1 |
| 4h | H4 |
| 1d | D1 |
| 1w | W1 |

Other intervals are rejected explicitly instead of being silently approximated. The adapter confirms the selected cTrader account is not live before account authentication. It converts trendbar prices using the Open API's relative-price fields and UTC minute timestamp.

## Transport boundary

The adapter receives a host-owned transport implementing:
- `connect()`
- `application_auth()`
- `account_details(account_id)` returning the selected account's `isLive` flag and account ID
- `account_auth(account_id)`
- `resolve_symbol(account_id, symbol)` returning symbol ID and digits
- `get_trendbars(account_id, symbol_id, period, count)`
- `status()` and `disconnect()`

The provider onboarding factory must create a distinct transport and adapter for each account using tenant-owned OAuth credentials. The adapter serializes historical trendbar requests to respect Spotware's five-requests-per-second historical-data limit per connection.

## Candle timestamp and session-boundary contract

Spotware defines `utcTimestampInMinutes` as the Unix timestamp (in minutes)
of the nominal start of the trendbar. The adapter converts it to an
timezone-aware UTC `datetime`; it does not reinterpret the value as local
computer time or broker-wall-clock time.

Intraday periods use fixed UTC interval buckets and require an exact
timestamp match before analysis or notification. Daily and weekly periods are
different: the tenant timeframe monitor now requires the provider adapter to
implement `expected_last_closed_candle(timeframe, symbol, now, close_grace_seconds)`.
The method must return a timezone-aware timestamp calculated from the verified
broker/account session calendar. If that capability is absent or returns an
invalid value, analysis is withheld with `WAITING_FOR_SESSION_CALENDAR`; stored
D1/W1 signals are also withheld from the active view with
`SESSION_CALENDAR_UNAVAILABLE`.

**cTrader D1/W1 remain blocked by default:** the transport now retrieves the
full symbol entity through `ProtoOASymbolByIdReq` and exposes the broker-supplied
`schedule`, `scheduleTimeZone`, and `holiday` metadata through
`get_symbol_session_calendar_metadata(symbol)`. The weekly intervals are
expressed as seconds from Sunday 00:00 in the supplied schedule timezone; each
holiday also carries its timezone/date and optional intraday bounds. The
adapter validates interval bounds, holiday date/bounds and required timezone
strings. It reports whether the current runtime could resolve each IANA timezone;
a Windows runtime without a timezone database may expose the raw metadata as
`NOT_VALIDATED_BY_RUNTIME`, but that status is never sufficient to calculate
a session boundary.

The adapter also exposes
`get_session_calendar_reconciliation_report(symbol, timeframe, lookback=120)`
for D1/W1. It returns the exact observed candle-open timestamps in UTC
and, when the runtime can resolve the broker timezone, in provider-local time
with UTC offsets, alongside aggregated open-time patterns and the broker's raw
session metadata. The report is explicitly
`OBSERVATIONS_ONLY_NOT_VALIDATED`; it never authorizes a signal, validates a
calendar, or enables execution. It is evidence for a later broker-specific
review, not an automatic approval.

This is a necessary input, not yet a verified D1/W1 candle calendar. The
adapter deliberately does **not** implement
`expected_last_closed_candle` from these fields alone. Before enabling it,
reconcile actual historical and live D1/W1 trendbar open timestamps against the
symbol schedule and broker aggregation convention, including daylight-saving
transitions, early closes, holidays and weekend reopen. A trading-hours
schedule does not, by itself, prove the exact daily/weekly candle roll time.
Do not weaken exact candle matching or substitute a guessed timezone.

If the full symbol request is unavailable or the timezone/schedule is
incomplete, metadata is reported unavailable/incomplete; intraday symbol
resolution remains usable, while D1/W1 continue to fail closed.

M1/M5 and other intraday periods are also matched by exact provider candle-open
timestamp and canonical timeframe; no timeframe may reuse another period's
statistics or candle history.

## Runtime integration and current limitation

The official Spotware DEMO transport is now implemented in
`integration/ctrader_openapi_readonly_transport.py`; tenant-scoped OAuth state,
encrypted token-vault contracts, account selection, refresh coordination and
restart recovery are implemented in the corresponding
`integration/tenant_ctrader_*` services. The transport is created server-side
with credentials resolved from the tenant-bound vault; the browser never receives
the application secret or OAuth tokens.

For accounts that complete the fresh OAuth/account handshake, the tenant session
registry binds one adapter to one tenant/subject/connection. The timeframe monitor
calls `subscribe_live_candles(symbol, timeframe, callback)`, accepts only closed,
valid candles for that exact account/symbol/timeframe, rejects callbacks from a
replaced adapter, and requires the candle timestamp expected for the selected
cycle before analysis. Persisted watches are rebound after a process restart only
after a new account handshake. The stream callback is therefore wired to the
multi-tenant monitor; it is not merely an unconnected adapter interface.

**Still not proven:** no real Spotware credentials or DEMO account handshake,
live quote/candle stream, OAuth rotation, reconnect or end-to-end signal cycle
has been evidenced in the hosted environment. The optional SDK, app credentials,
redirect URI, OAuth secret exchange, KMS-backed production token cipher and
shared refresh lease must be provisioned there. Until that evidence exists, the
repository implementation must not be described as a live connected cTrader
account. The account mode is hard-restricted to DEMO and the adapter remains
read-only; it has no order placement or money-movement methods.

## Official references

- cTrader Open API: https://help.ctrader.com/open-api/
- Historical and live trendbars: https://help.ctrader.com/open-api/symbol-data/
- Account authentication: https://help.ctrader.com/open-api/account-authentication/
- Python SDK: https://help.ctrader.com/open-api/python-SDK/python-sdk-index/
- Spotware OpenApiPy sample: https://github.com/spotware/OpenApiPy

### Subscription diagnostics

The subscription diagnostics use the same provider-specific session-boundary resolver as analysis and delayed notification dispatch. For D1/W1, when the adapter cannot provide a verified boundary, `expected_last_closed_candle_at` is `null`, and both `data_freshness_state` and `live_stream_status` report `SESSION_CALENDAR_UNAVAILABLE`. These fields must not be replaced with a generic UTC-derived freshness estimate. Intraday subscriptions continue to report their fixed-UTC candle boundary, with exact provider timestamp matching.
