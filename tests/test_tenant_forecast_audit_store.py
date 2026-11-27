from __future__ import annotations

import pytest

from analysis.tenant_forecast_audit_store import TenantForecastAuditStore
from security.tenant_context import TenantContext


def test_forecast_must_be_recorded_before_outcome_and_is_tenant_scoped(tmp_path):
    store = TenantForecastAuditStore(tmp_path / "forecast-audit.sqlite3")
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    other_tenant = TenantContext("tenant-b", "alice")

    recorded = store.record_forecast(
        alice,
        forecast_id="forecast-1",
        symbol="eurusd",
        timeframe="M1",
        direction="COMPRA",
        model_version="model-v1",
        probability=0.72,
        forecast_at="2026-11-27T10:00:00+00:00",
    )
    assert recorded["timeframe"] == "1m"
    assert recorded["calibration_status"] == "PENDING_OUTCOME"
    assert store.calibration_records(alice) == []
    assert store.calibration_records(bob) == []
    assert store.calibration_records(other_tenant) == []

    resolved = store.resolve_forecast(
        alice,
        "forecast-1",
        outcome=True,
        resolved_at="2026-11-27T10:01:00+00:00",
        provenance="REAL_MARKET_DATA",
    )
    assert resolved["resolved"] is True
    rows = store.calibration_records(alice)
    assert len(rows) == 1
    assert rows[0]["timeframe"] == "1m"
    assert rows[0]["probability"] == 0.72
    assert rows[0]["outcome"] is True
    assert rows[0]["out_of_sample"] is True


def test_forecast_outcome_cannot_be_resolved_from_manual_or_simulated_labels(tmp_path):
    store = TenantForecastAuditStore(tmp_path / "forecast-audit.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    store.record_forecast(
        owner, forecast_id="forecast-2", symbol="EURUSD", timeframe="M5",
        direction="VENDA", model_version="model-v1", probability=0.4,
        forecast_at="2026-11-27T10:00:00Z",
    )
    with pytest.raises(ValueError):
        store.resolve_forecast(
            owner, "forecast-2", outcome=False,
            resolved_at="2026-11-27T10:05:00Z", provenance="SIMULATED_DEMO",
        )
    with pytest.raises(ValueError):
        store.resolve_forecast(
            owner, "forecast-2", outcome=False,
            resolved_at="2026-11-27T10:05:00Z", provenance="MANUAL_STUDY",
        )
    assert store.calibration_records(owner) == []


def test_forecast_timestamp_must_precede_resolution_and_resolution_is_immutable(tmp_path):
    store = TenantForecastAuditStore(tmp_path / "forecast-audit.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    store.record_forecast(
        owner, forecast_id="forecast-3", symbol="EURUSD", timeframe="M5",
        direction="COMPRA", model_version="model-v1", probability=0.6,
        forecast_at="2026-11-27T10:00:00Z",
    )
    with pytest.raises(ValueError):
        store.resolve_forecast(
            owner, "forecast-3", outcome=True,
            resolved_at="2026-11-27T09:59:00Z", provenance="REAL_MARKET_DATA",
        )
    store.resolve_forecast(
        owner, "forecast-3", outcome=True,
        resolved_at="2026-11-27T10:05:00Z", provenance="REAL_MARKET_DATA",
    )
    with pytest.raises(ValueError):
        store.resolve_forecast(
            owner, "forecast-3", outcome=False,
            resolved_at="2026-11-27T10:06:00Z", provenance="REAL_MARKET_DATA",
        )


def test_invalid_probability_timeframe_and_identity_are_rejected(tmp_path):
    store = TenantForecastAuditStore(tmp_path / "forecast-audit.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    with pytest.raises(ValueError):
        store.record_forecast(
            owner, forecast_id="bad-p", symbol="EURUSD", timeframe="M1",
            direction="COMPRA", model_version="model-v1", probability=1.2,
            forecast_at="2026-11-27T10:00:00Z",
        )
    with pytest.raises(ValueError):
        store.record_forecast(
            owner, forecast_id="bad-tf", symbol="EURUSD", timeframe="M60",
            direction="COMPRA", model_version="model-v1", probability=0.5,
            forecast_at="2026-11-27T10:00:00Z",
        )
    with pytest.raises(PermissionError):
        store.calibration_records({"tenant_id": "tenant-a", "subject_id": "alice"})
