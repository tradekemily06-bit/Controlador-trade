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
implement `expected_last_closed_candle(timeframe, now, close_grace_seconds)`.
The method must return a timezone-aware timestamp calculated from the verified
broker/account session calendar. If that capability is absent or returns an
invalid value, analysis is withheld with `WAITING_FOR_SESSION_CALENDAR`; stored
D1/W1 signals are also withheld from the active view with
`SESSION_CALENDAR_UNAVAILABLE`.

**cTrader D1/W1 remain blocked by default:** the current adapter does not yet
implement a verified broker-session calendar. A UTC timestamp does not by
itself prove that the broker's D1/W1 session boundary matches a UTC bucket.
Before implementing that capability, compare actual historical and live bar
open timestamps with the broker/account's documented session convention,
including daylight-saving transitions and weekend reopen. Do not weaken exact
candle matching or substitute a guessed timezone.

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
