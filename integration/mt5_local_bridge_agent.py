from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from core.p122_broker_market_data import BrokerMarketDataRequest
from execution.icmarkets_mt5_market_data import ICMarketsMT5DemoMarketDataAdapter


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} precisa estar configurada")
    return value


def _post_json(url: str, token: str, payload: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            if response.status not in (200, 202):
                raise RuntimeError(f"relay HTTP status {response.status}")
            return result
    except urllib.error.HTTPError as exc:
        # Never print request headers or tokens in error messages.
        raise RuntimeError(f"relay rejeitou lote: HTTP {exc.code}") from exc


def publish_once(
    adapter: ICMarketsMT5DemoMarketDataAdapter,
    relay_url: str,
    token: str,
    symbols: list[str],
    timeframes: list[str],
    limit: int = 250,
    source_id: str = "mt5-local",
) -> int:
    if adapter.get_account_mode() != "DEMO":
        raise RuntimeError("terminal MT5 não confirmou conta DEMO")
    sent = 0
    for symbol in symbols:
        for timeframe in timeframes:
            request = BrokerMarketDataRequest(symbol, timeframe, limit)
            candles = adapter.fetch_market_data(request)
            if not candles:
                continue
            payload = {
                "source_id": source_id,
                "account_mode": "DEMO",
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": [
                    {
                        "timestamp": candle.timestamp.isoformat(),
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                    }
                    for candle in candles
                ],
            }
            _post_json(relay_url, token, payload)
            sent += len(candles)
    return sent


def main() -> None:
    base_url = _required("CONTROLADOR_MT5_RELAY_URL").rstrip("/")
    if not base_url.lower().startswith("https://"):
        raise RuntimeError("CONTROLADOR_MT5_RELAY_URL deve usar HTTPS")
    token = _required("CONTROLADOR_MT5_RELAY_TOKEN")
    symbols = [item.strip().upper() for item in _required("CONTROLADOR_MT5_SYMBOLS").split(",") if item.strip()]
    timeframes = [item.strip().upper() for item in _required("CONTROLADOR_MT5_TIMEFRAMES").split(",") if item.strip()]
    if not symbols or not timeframes:
        raise RuntimeError("configure ao menos um símbolo e um timeframe")
    interval = max(2.0, float(os.getenv("CONTROLADOR_MT5_RELAY_INTERVAL", "5")))
    limit = min(500, max(20, int(os.getenv("CONTROLADOR_MT5_RELAY_CANDLE_LIMIT", "250"))))
    source_id = os.getenv("CONTROLADOR_MT5_RELAY_SOURCE_ID", "mt5-local").strip() or "mt5-local"
    adapter = ICMarketsMT5DemoMarketDataAdapter()
    relay_url = base_url + "/api/bridge/mt5/candles"
    while True:
        started = time.monotonic()
        try:
            count = publish_once(adapter, relay_url, token, symbols, timeframes, limit, source_id)
            print(f"MT5 relay: {count} candles enviados; conta DEMO confirmada")
        except Exception as exc:
            # Error messages are bounded and never include secrets.
            print(f"MT5 relay indisponível: {str(exc)[:240]}")
        elapsed = time.monotonic() - started
        time.sleep(max(0.5, interval - elapsed))


if __name__ == "__main__":
    main()
