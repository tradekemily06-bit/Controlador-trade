from datetime import datetime, timedelta, timezone

import pytest

from core.indicator_sources import (
    ExternalIndicatorReading,
    IndicatorSourceKind,
    is_fresh_indicator_reading,
)


def reading(**overrides):
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    values = dict(
        provider="test-provider",
        source_kind=IndicatorSourceKind.EXTERNAL_SITE,
        symbol="EURUSD",
        timeframe="M5",
        observed_at=now,
        candle_timestamp=now - timedelta(minutes=5),
        values={"rsi_14": 53.2, "macd": 0.001},
    )
    values.update(overrides)
    # Keep the candle time before observation time even when testing old observations.
    if "observed_at" in overrides and "candle_timestamp" not in overrides:
        values["candle_timestamp"] = overrides["observed_at"] - timedelta(minutes=5)
    return ExternalIndicatorReading(**values)


def test_accepts_normalized_external_indicator_reading():
    result = reading()
    assert result.source_kind is IndicatorSourceKind.EXTERNAL_SITE
    assert result.values["rsi_14"] == 53.2


def test_rejects_non_finite_indicator_values():
    with pytest.raises(ValueError, match="finite numeric"):
        reading(values={"rsi_14": float("nan")})


def test_rejects_future_candle_timestamp():
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="after observation"):
        reading(candle_timestamp=now + timedelta(seconds=1))


def test_freshness_rejects_old_and_future_observations():
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    assert is_fresh_indicator_reading(reading(), now=now)
    assert not is_fresh_indicator_reading(
        reading(observed_at=now - timedelta(minutes=10)),
        now=now,
    )
    assert not is_fresh_indicator_reading(
        reading(observed_at=now + timedelta(seconds=1)),
        now=now,
    )


def test_requires_timezone_aware_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        reading(observed_at=datetime(2026, 10, 10, 12))


def test_indicator_visibility_toggle_is_saved_in_shared_ecosystem_preferences():
    html = ( __import__("pathlib").Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="indicatorsDefault"' in html
    assert 'indicators_enabled:$(\'indicatorsDefault\').checked' in html
    assert 'body:JSON.stringify({indicators_enabled:$(\'indicatorsDefault\').checked})' in html
    assert "Indicadores ocultos nas preferências do ecossistema." in html
    assert "@media(max-width:719px)" in html
    assert ".grid{grid-template-columns:minmax(0,1fr)" in html
    assert ".chart-svg{height:65vw;min-height:220px}" in html
    assert "localStorage" not in html
