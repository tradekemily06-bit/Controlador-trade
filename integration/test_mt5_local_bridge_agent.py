from datetime import datetime, timezone

from data.models import Candle
from integration import mt5_local_bridge_agent as agent


class FakeDemoAdapter:
    def get_account_mode(self):
        return "DEMO"

    def fetch_market_data(self, request):
        return (
            Candle(datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc), 1.1, 1.2, 1.0, 1.15, 100),
        )


def test_publish_once_posts_only_confirmed_demo_candles(monkeypatch):
    sent = []
    monkeypatch.setattr(agent, "_post_json", lambda url, token, payload: sent.append((url, token, payload)) or {"accepted": 1})

    count = agent.publish_once(
        FakeDemoAdapter(), "https://example.test/api/bridge/mt5/candles",
        "secret", ["EURUSD"], ["M5"], limit=20,
    )

    assert count == 1
    url, token, payload = sent[0]
    assert url.startswith("https://")
    assert token == "secret"
    assert payload["account_mode"] == "DEMO"
    assert payload["symbol"] == "EURUSD"
    assert payload["message_id"]
    assert payload["sent_at"]
    assert len(payload["candles"]) == 1


def test_publish_once_refuses_unconfirmed_account(monkeypatch):
    class RealAdapter(FakeDemoAdapter):
        def get_account_mode(self):
            return "REAL"

    monkeypatch.setattr(agent, "_post_json", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not send")))
    try:
        agent.publish_once(RealAdapter(), "https://example.test", "secret", ["EURUSD"], ["M5"])
    except RuntimeError as exc:
        assert "DEMO" in str(exc)
    else:
        raise AssertionError("expected DEMO account guard")
