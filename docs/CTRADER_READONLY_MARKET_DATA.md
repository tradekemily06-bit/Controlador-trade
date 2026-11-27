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

## Current limitation

This commit implements and tests the adapter contract, DEMO validation, timeframe mapping and price normalization. It does **not** yet include the production Twisted/Spotware transport lifecycle, OAuth authorization callback, refresh-token vault integration or a real cTrader account handshake. Therefore cTrader is not yet a live connected provider in the application. Do not mark it CONNECTED until the host transport is implemented and verified against a real DEMO account.

The adapter exposes only read-only candle retrieval. It does not expose order placement or money movement.

## Official references

- cTrader Open API: https://help.ctrader.com/open-api/
- Historical and live trendbars: https://help.ctrader.com/open-api/symbol-data/
- Account authentication: https://help.ctrader.com/open-api/account-authentication/
- Python SDK: https://help.ctrader.com/open-api/python-SDK/python-sdk-index/
- Spotware OpenApiPy sample: https://github.com/spotware/OpenApiPy
