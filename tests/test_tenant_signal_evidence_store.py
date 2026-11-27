from __future__ import annotations

import pytest

from analysis.tenant_signal_evidence_store import TenantSignalEvidenceStore
from security.tenant_context import TenantContext


def _record(store, owner, signal_id="s-1", timeframe="M1", **overrides):
    values = {
        "signal_id": signal_id,
        "symbol": "eurusd",
        "timeframe": timeframe,
        "direction": "COMPRA",
        "model_version": "technical-v1",
        "evidence_score": 75.0,
        "score_semantics": "EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY",
        "candle_close_at": "2026-11-27T10:01:00Z",
        "observed_at": "2026-11-27T10:01:02Z",
        "valid_until": "2026-11-27T10:02:00Z",
        "provenance": "REAL_MARKET_DATA",
    }
    values.update(overrides)
    return store.record_signal(owner, **values)


def test_signal_evidence_is_tenant_scoped_and_keeps_timeframes_separate(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals.sqlite3")
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    other = TenantContext("tenant-b", "alice")

    first = _record(store, alice, "m1-1", "M1")
    second = _record(
        store, alice, "m5-1", "M5",
        candle_close_at="2026-11-27T10:05:00Z",
        observed_at="2026-11-27T10:05:02Z",
        valid_until="2026-11-27T10:10:00Z",
    )
    assert first["timeframe"] == "1m"
    assert second["timeframe"] == "5m"
    assert first["score_type"] == "EVIDENCE_STRENGTH"
    assert first["probability_of_profit"] is None
    assert [x["timeframe"] for x in store.list_signals(alice)] == ["1m", "5m"]
    assert store.list_signals(alice, timeframe="M1")[0]["signal_id"] == "m1-1"
    assert store.list_signals(alice, timeframe="5m")[0]["signal_id"] == "m5-1"
    assert store.list_signals(bob) == []
    assert store.list_signals(other) == []


def test_signal_evidence_rejects_probability_semantics_and_invalid_scores(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    with pytest.raises(ValueError):
        _record(store, owner, "bad-semantics", score_semantics="75_PERCENT_WIN_CHANCE")
    with pytest.raises(ValueError):
        _record(store, owner, "bad-score", evidence_score=101)
    with pytest.raises(ValueError):
        _record(store, owner, "bool-score", evidence_score=True)


def test_signal_evidence_requires_real_market_data_provenance(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    with pytest.raises(ValueError):
        _record(store, owner, "demo-label", provenance="SIMULATED_DEMO")
    with pytest.raises(ValueError):
        _record(store, owner, "manual-label", provenance="MANUAL_STUDY")


def test_signal_evidence_requires_closed_candle_and_future_expiry(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    with pytest.raises(ValueError):
        _record(store, owner, "early-analysis", observed_at="2026-11-27T10:00:59Z")
    with pytest.raises(ValueError):
        _record(store, owner, "expired-at-write", valid_until="2026-11-27T10:01:02Z")
    with pytest.raises(ValueError):
        _record(store, owner, "naive-time", observed_at="2026-11-27T10:01:02")


def test_signal_evidence_rejects_untrusted_context_shape(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals.sqlite3")
    with pytest.raises(PermissionError):
        store.list_signals({"tenant_id": "tenant-a", "subject_id": "alice"})


def test_signal_evidence_capture_is_idempotent_after_restart(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    first = _record(store, owner, "restart-duplicate")
    repeated = _record(store, owner, "restart-duplicate")
    assert first["audit_status"] == "RECORDED"
    assert repeated["audit_status"] == "ALREADY_RECORDED"
    assert len(store.list_signals(owner)) == 1


def test_signal_evidence_id_cannot_be_reused_for_different_evidence(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    _record(store, owner, "immutable-id")
    with pytest.raises(ValueError, match="different immutable evidence"):
        _record(store, owner, "immutable-id", direction="VENDA")

def test_signal_evidence_rejects_tampered_noncanonical_tenant_context(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals-context.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    object.__setattr__(owner, "subject_id", "alice" + chr(10))
    with pytest.raises(PermissionError):
        _record(store, owner)




def test_signal_evidence_rejects_non_finite_and_unrepresentable_scores(tmp_path):
    store = TenantSignalEvidenceStore(tmp_path / "signals-score-bounds.sqlite3")
    owner = TenantContext("tenant-a", "alice")
    for index, score in enumerate((float("nan"), float("inf"), float("-inf"), 10**1000)):
        with pytest.raises(ValueError):
            _record(store, owner, f"invalid-score-{index}", evidence_score=score)

