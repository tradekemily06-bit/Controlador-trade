from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
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


def build_relay_endpoint(base_url: str, connection_id: str | None = None) -> str:
    base = base_url.rstrip("/")
    if not base.lower().startswith("https://"):
        raise ValueError("relay URL deve usar HTTPS")
    if connection_id is None or not connection_id.strip():
        return base + "/api/bridge/mt5/candles"
    connection = connection_id.strip()
    if not re.fullmatch(r"[a-f0-9]{32}", connection):
        raise ValueError("CONTROLADOR_MT5_RELAY_CONNECTION_ID inválido")
    return base + f"/api/bridge/mt5/connections/{connection}/candles"


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
    account_reference_reader = getattr(adapter, "get_account_reference", None)
    if not callable(account_reference_reader):
        raise RuntimeError("adapter MT5 não oferece referência estável da conta")
    account_reference = account_reference_reader()
    if not isinstance(account_reference, str) or not re.fullmatch(r"mt5_[a-f0-9]{32}", account_reference):
        raise RuntimeError("referência pseudônima da conta MT5 inválida")
    sent = 0
    for symbol in symbols:
        for timeframe in timeframes:
            request = BrokerMarketDataRequest(symbol, timeframe, limit)
            candles = adapter.fetch_market_data(request)
            if not candles:
                continue
            payload = {
                "source_id": source_id,
                "account_reference": account_reference,
                "message_id": str(uuid.uuid4()),
                "sent_at": datetime.now(timezone.utc).isoformat(),
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
    connection_id = os.getenv("CONTROLADOR_MT5_RELAY_CONNECTION_ID", "").strip() or None
    source_id = os.getenv("CONTROLADOR_MT5_RELAY_SOURCE_ID", "").strip()
    if connection_id is not None and not source_id:
        raise RuntimeError("CONTROLADOR_MT5_RELAY_SOURCE_ID é obrigatório no modo multi-conta")
    if not source_id:
        source_id = "mt5-local"
    adapter = ICMarketsMT5DemoMarketDataAdapter()
    relay_url = build_relay_endpoint(base_url, connection_id)
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
