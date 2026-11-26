# Unified intelligence and standalone application boundary

## Target architecture

The product has seven user-facing areas, all routed through one shared intelligence coordinator:

1. Cabine de Comando
2. Análise
3. Estudo
4. Memória
5. Reserva Fiscal
6. Assistente do Ecossistema
7. Central

The 45+ senior experience baseline, specialist domains, financial-market curriculum, reasoning, memory, research, risk, audit and security are internal capabilities. They are not additional navigation areas.

## Safety and truthfulness

- The application is an analyst and information system; this layer never submits broker orders.
- Every route and area contract has execution_authorized=false.
- Learning, research and discoveries do not become operational rules without evidence and validation.
- Missing area handlers are reported as NOT_CONNECTED; no integration is fabricated.
- AGI/ASI is a research ambition, not a verified property or marketing claim.
- A shared intelligence coordinator does not by itself provide a foundation model, live market feed, persistent multi-tenant storage or push delivery.

## Implementation status of this first slice

This change adds the shared intelligence contract, the seven-area registry, the read-only application facade and tests. It does not claim that all seven functional services, providers, authentication, fiscal data sources, live feeds, mobile push or deployment have been connected. Those require individual adapters, credentials/configuration where applicable, integration tests and production validation.

The approved Lovable interface is outside this change and must remain visually unchanged.

## Existing service wiring

The standalone application factory now composes the current ecosystem service, senior contextual reasoning, learning/curriculum, operational memory, read-only fiscal summaries and the read-only assistant behind the same intelligence object. Fiscal owner identity is injected from trusted server configuration, never from a request.

Only services actually supplied to the factory are marked CONNECTED. The analysis area requires a validated market-context object from a market-data adapter. Fiscal and assistant areas remain NOT_CONNECTED until their persistent stores, trusted identity and provider are configured. No order or money movement is exposed.


## Broker-neutral market analysis

The standalone Analysis area can receive any provider implementing the existing MarketDataProvider contract. Its feed is normalized and validated, then passed through the existing strategy pipeline, signal-quality evaluator, market-context engine and the shared senior-context gate. It returns a candidate signal and evidence score only; it never submits orders. The standalone response includes a structured manual-review signal card (symbol, direction, timeframe and evidence score). The score is explicitly not a win probability; probability of profit, entry, stop-loss and take-profit remain unset unless separately estimated and validated. Stale, gapped, invalid or unsupported-timeframe data force AGUARDAR.

The timeframe parser now accepts normalized platform forms such as `M1`, `M2`, `M5`, `M10`, `M15`, `M20`, `M30`, `H1`, `H2`, `H4`, `H6`, `H8`, `H12`, `D1`, `D2` and `W1`, as well as compact forms such as `1m`, `2m`, `10m`, `1h`, `2h`, `1d` and `1w`. The current bounded syntax accepts 1–59 minute intervals, 1–24 hour intervals, 1–31 day intervals and 1–4 week intervals. No market-data provider is enabled by default. The standalone runtime supports explicit server-side opt-in to the read-only BiQuote OHLC adapter with `CONTROLADOR_MARKET_DATA_PROVIDER=biquote`, or the local Windows MT5 DEMO adapter with `CONTROLADOR_MARKET_DATA_PROVIDER=mt5_demo`; BiQuote is not a connected brokerage account and does not establish DEMO/REAL mode. The adapter derives custom fixed intervals from complete, closed base candles available at 1m, 5m, 1h or 1d, selecting a base interval that divides the requested interval. Aggregated candles are emitted only when all expected source candles are contiguous and aligned to the target bucket; incomplete buckets and gaps are discarded, never estimated. The provider caps each source request at 1,000 bars, so very large timeframes or deep history may return fewer candles; if there are not enough valid candles, the analysis pipeline must wait rather than invent data. The existing read-only MT5 DEMO adapter recognizes its standard native intervals M1/M2/M3/M4/M5/M6/M10/M12/M15/M20/M30, H1/H2/H3/H4/H6/H8/H12, D1 and W1. It is now registered as an explicit standalone provider using `CONTROLADOR_MARKET_DATA_PROVIDER=mt5_demo` (or `icmarkets_mt5_demo`) and reports `DEMO` only after checking the connected terminal and account; REAL accounts and disconnected terminals fail closed. This adapter requires the Python `MetaTrader5` package and a running MT5 terminal on the same Windows machine as the standalone runtime; the optional dependency is listed in `requirements-mt5.txt` and must be installed in that Windows runtime. A cloud-hosted runtime cannot directly reach an MT5 terminal on a user's separate computer; that deployment requires a separately secured local-to-cloud bridge, which is not implemented here. Non-native MT5 intervals still require a separate resampling adapter. The endpoint, symbol coverage, freshness and availability still require a live connection test in the target environment. Other providers must be injected through the provider registry; unsupported configuration fails closed. A provider being registered is not proof of a live connection. The accepted timeframe format does not itself implement an automatic scheduler: automatic refresh at each candle close is a separate runtime task and must be validated independently. A configured API model is separate from the market-data feed and does not make the system an AGI/ASI.

### Calibrated probability of profit (DEMO and REAL)

The product requirement is to show a probability-of-profit estimate in addition to the technical evidence score, for both DEMO and REAL contexts. These are distinct measures and must never be substituted for one another.

- The probability is conditional on a fully specified trade hypothesis: symbol, direction, timeframe, entry/exit rules, stop/target or other outcome horizon, and costs. It must estimate net-positive outcome, not merely whether price moved in the predicted direction.
- Calibration and validation must be segmented by execution context (DEMO versus REAL) and, where evidence supports it, provider/broker, account type, symbol, timeframe and strategy. DEMO fills are not assumed to represent REAL spread, slippage, latency, rejection or liquidity.
- Training and evaluation must use time-ordered, out-of-sample data; prevent leakage between overlapping trades; report sample count, evaluation window, calibration quality and uncertainty interval. A high technical score alone is never a probability estimate.
- Until a segment has sufficient representative, validated outcomes, the UI/API must show “probabilidade indisponível / ainda não calibrada” rather than inventing a percentage. Do not silently borrow DEMO calibration for REAL or vice versa.
- Historical outcomes must distinguish DEMO and REAL and record the actual entry/exit, costs and outcome source. Manual labels must be identified as manual and must not be treated as verified broker fills.
- This remains an analyst feature only. Probability is informational, not a guarantee or an instruction to enter; the user decides and places any trade manually.


## Functional module placement (no extra navigation areas)

| Existing module/function | Destination |
| --- | --- |
| Market data, chart reading, signals, score, decision quality | Analysis |
| Market news, statistics and performance summaries | Analysis |
| Reports and export | Analysis / Memory, depending on whether the user is analyzing or retrieving history |
| Laboratory, replay, simulator, Professor, curriculum and learning resources | Study |
| Decision journal, outcomes, operational history, audit trail and validated knowledge | Memory |
| Command/status dashboard, risk state, kill switch and operational alerts | Command Cabin |
| Brazilian and foreign fiscal queues, records and document review | Tax Reserve |
| Cross-area explanations and read-only questions | Ecosystem Assistant |
| Broker/provider connections, preferences, identity, access, security and configuration | Central |

Risk, senior expertise, market context, research, security and audit policies are shared internal services. They do not create extra navigation areas. A module gets a separate area only if it represents a genuinely distinct user workflow that cannot reasonably live inside one of the seven existing areas.

## Active DEMO / REAL validation mode

The selected market-data provider may expose `get_account_mode()`. The standalone provider registry resolves that value and includes a single verified `account_mode` object in `/api/market-data/providers`:
- `DEMO` or `REAL` only when the selected adapter explicitly reports that mode;
- `UNAVAILABLE` with a null mode when there is no selected adapter, the adapter does not expose the capability, returns an invalid value, or raises an error.
The UI must never display both modes together and must not infer account mode from a user preference or from the market-data feed name. This is a capability contract, not proof that a live broker adapter currently implements it. Provider registration remains distinct from live connection validation.

## Integration status must be honest

A route being registered is not the same as a production integration. Each area and module must distinguish: implemented in the repository, wired to the standalone runtime, provider configured, live connection tested, persistent storage verified, and end-to-end behavior tested. Current market news provider remains unconfigured. Analysis and Memory now expose a JSON report built from the standalone DecisionRecord model; it deliberately does not coerce those records into the distinct legacy OperationMemoryRecord model. Study records (sources, resources, observations, activities and attempts) are persisted through the versioned LearningStateStore when the standalone runtime supplies the shared SQLite state store. Notifications are restored and persisted through that same store and are exposed in Command Cabin; this is durable in-app notification state, not external push delivery. Mobile/web push delivery, subscriptions, background delivery and end-to-end notification testing remain unimplemented.


## Automatic candle-close monitoring

When a read-only market-data provider is configured, the standalone runtime starts a background monitor. It stores watch subscriptions in SQLite and evaluates each subscribed symbol/timeframe after the expected candle close, with a short grace period for provider publication. It verifies that the provider returned the exact expected closed candle before recording a cycle; stale or not-yet-published candles remain waiting and are retried. Subscriptions survive a process restart, but the worker itself runs only while the standalone server process is alive.

The monitor accepts the same normalized timeframe syntax as the analysis service. It records results per symbol/timeframe/candle, avoids reprocessing the same candle, and creates an in-app market notification when the signal changes materially. It never submits orders. This does not by itself provide delivery to a phone/browser while the app window is closed: the backend must be hosted as a persistent service and an external push provider/worker still needs to be configured and end-to-end tested.

API routes (protected by the existing standalone access boundary):
- `GET /api/market-monitor/status` — worker and subscription status.
- `GET /api/market-monitor/subscriptions` — persisted watch list.
- `GET /api/market-monitor/results?limit=50` — latest persisted analysis cycles (limit 1–200).
- `POST /api/market-monitor/subscriptions` — body: `{"symbol":"EURUSD","timeframe":"M5"}`.
- `DELETE /api/market-monitor/subscriptions` — body: `{"symbol":"EURUSD","timeframe":"M5"}`.

The API is backend capability only. The approved Lovable interface has not been modified or wired to these endpoints yet.


## Secure local MT5-to-cloud relay (DEMO, read-only)

The MT5 terminal is a Windows-local process. A cloud-hosted API cannot pull data directly from a terminal behind the user's router. The optional relay uses an outbound HTTPS connection from a small local Windows agent to the standalone API; no inbound port is opened on the user's PC.

- Cloud runtime: set `CONTROLADOR_MARKET_DATA_PROVIDER=mt5_relay`, configure a high-entropy `CONTROLADOR_MT5_RELAY_TOKEN` as a server secret, and enable the normal remote-access boundary separately. The relay token is independent from the UI/API access token.
- TLS: the local agent refuses non-HTTPS URLs. The API accepts relay writes only over direct HTTPS, or when `CONTROLADOR_TRUST_PROXY_TLS=true` is explicitly set behind a trusted TLS-terminating reverse proxy. Do not set that flag behind an untrusted proxy.
- Local Windows agent: install the optional dependency from `requirements-mt5.txt`, configure `CONTROLADOR_MT5_RELAY_URL`, `CONTROLADOR_MT5_RELAY_TOKEN`, `CONTROLADOR_MT5_SYMBOLS`, and `CONTROLADOR_MT5_TIMEFRAMES`, then run `python -m integration.mt5_local_bridge_agent`. It reads only closed candles and confirms DEMO before sending.
- The cloud endpoint `POST /api/bridge/mt5/candles` validates the token, TLS boundary, symbol/timeframe, candle shape, DEMO assertion, message timestamp and unique message ID. It stores bounded candle history in SQLite. The relay account mode becomes DEMO only while a recent heartbeat is present; otherwise it is UNAVAILABLE.
- The endpoint accepts no orders, account credentials, positions or money movement. The bridge sends market candles only. It does not expose the local terminal to inbound internet traffic.
- The relay is opt-in and not live-tested merely by being implemented. Production use still requires deployment of the cloud API, provisioning the two independent secrets, running the Windows agent on the same PC as MT5, confirming the relay status endpoint, and validating real closed-candle freshness for each selected symbol/timeframe. Do not describe it as connected until these steps pass.
- The local agent currently sends only the configured symbols/timeframes; adding a new one requires adding it to the agent configuration. The API's relay store is bounded and uses a recent heartbeat; it is not a historical market-data archive.

API:
- `POST /api/bridge/mt5/candles` — separate relay bearer token and TLS required.
- `GET /api/bridge/mt5/status` — normal standalone API authorization required.
