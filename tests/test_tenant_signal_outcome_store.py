from __future__ import annotations

import pytest

from analysis.tenant_signal_evidence_store import TenantSignalEvidenceStore
from analysis.tenant_signal_outcome_store import TenantSignalOutcomeStore
from security.tenant_context import TenantContext


def _store(tmp_path):
    evidence = TenantSignalEvidenceStore(tmp_path / "audit.sqlite3")
    outcomes = TenantSignalOutcomeStore(evidence)
    return evidence, outcomes


def _signal(evidence, owner, signal_id="s-1", timeframe="M1"):
    return evidence.record_signal(
        owner,
        signal_id=signal_id,
        symbol="EURUSD",
        timeframe=timeframe,
        direction="COMPRA",
        model_version="technical-v1",
        evidence_score=75,
        score_semantics="EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY",
        candle_close_at="2026-11-27T10:01:00Z",
        observed_at="2026-11-27T10:01:02Z",
        valid_until="2026-11-27T10:02:00Z",
        provenance="REAL_MARKET_DATA",
    )


def _candle(**changes):
    value = {
        "symbol": "EURUSD",
        "timeframe": "M1",
        "open_time": "2026-11-27T10:01:00Z",
        "open": 1.1500,
        "high": 1.1510,
        "low": 1.1490,
        "close": 1.1508,
    }
    value.update(changes)
    return value


def test_outcome_is_persisted_once_and_scoped_to_owner(tmp_path):
    evidence, outcomes = _store(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    other = TenantContext("tenant-b", "alice")
    _signal(evidence, alice)

    resolved = outcomes.resolve(
        alice, "s-1", _candle(), provenance="REAL_MARKET_DATA"
    )
    assert resolved["outcome"] is True
    assert outcomes.list_outcomes(alice)[0]["outcome"] is True
    assert outcomes.list_outcomes(bob) == []
    assert outcomes.list_outcomes(other) == []
    with pytest.raises(ValueError):
        outcomes.resolve(alice, "s-1", _candle(), provenance="REAL_MARKET_DATA")


def test_outcome_resolution_rejects_cross_tenant_and_wrong_timeframe(tmp_path):
    evidence, outcomes = _store(tmp_path)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    _signal(evidence, alice)
    with pytest.raises(LookupError):
        outcomes.resolve(bob, "s-1", _candle(), provenance="REAL_MARKET_DATA")
    with pytest.raises(ValueError):
        outcomes.resolve(
            alice, "s-1", _candle(timeframe="M5"),
            provenance="REAL_MARKET_DATA",
        )
    assert outcomes.list_outcomes(alice) == []


def test_doji_is_stored_as_unresolved_not_forced_to_loss(tmp_path):
    evidence, outcomes = _store(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    _signal(evidence, owner)
    result = outcomes.resolve(
        owner, "s-1", _candle(close=1.1500), provenance="REAL_MARKET_DATA"
    )
    assert result["outcome"] is None
    assert outcomes.list_outcomes(owner)[0]["outcome_status"] == "UNRESOLVED_DOJI"


def test_outcome_store_never_reports_profit_or_calibration(tmp_path):
    evidence, outcomes = _store(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    _signal(evidence, owner)
    result = outcomes.resolve(
        owner, "s-1", _candle(), provenance="REAL_MARKET_DATA"
    )
    assert result["net_profit_status"] == "NOT_ASSESSED"
    assert result["probability_of_profit"] is None
    assert result["calibration_eligible"] is False


def test_closed_candle_resolves_only_the_matching_provider_connection(tmp_path):
    evidence, outcomes = _store(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    _signal(evidence, owner, "account-a-signal")
    evidence.record_signal(
        owner, signal_id="account-b-signal", source_id="connection-b",
        symbol="EURUSD", timeframe="M1", direction="COMPRA",
        model_version="technical-v1", evidence_score=75,
        score_semantics="EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY",
        candle_close_at="2026-11-27T10:01:00Z",
        observed_at="2026-11-27T10:01:02Z",
        valid_until="2026-11-27T10:02:00Z",
        provenance="REAL_MARKET_DATA",
    )
    resolved = outcomes.resolve_pending_for_candle(
        owner, source_id="UNSCOPED", candle=_candle(),
        provenance="REAL_MARKET_DATA",
    )
    assert [item["signal_id"] for item in resolved] == ["account-a-signal"]
    assert [item["signal_id"] for item in outcomes.list_outcomes(owner)] == ["account-a-signal"]
    assert outcomes.resolve_pending_for_candle(
        owner, source_id="connection-b", candle=_candle(),
        provenance="REAL_MARKET_DATA",
    )[0]["signal_id"] == "account-b-signal"


def test_wait_decision_is_not_sent_to_directional_resolver(tmp_path):
    evidence, outcomes = _store(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    evidence.record_signal(
        owner, signal_id="wait-signal", source_id="account-1",
        symbol="EURUSD", timeframe="M1", direction="AGUARDAR",
        model_version="technical-v1", evidence_score=40,
        score_semantics="EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY",
        candle_close_at="2026-11-27T10:01:00Z",
        observed_at="2026-11-27T10:01:02Z",
        valid_until="2026-11-27T10:02:00Z",
        provenance="REAL_MARKET_DATA",
    )
    assert outcomes.resolve_pending_for_candle(
        owner, source_id="account-1", candle=_candle(),
        provenance="REAL_MARKET_DATA",
    ) == []
    assert outcomes.list_outcomes(owner) == []


def test_outcome_store_rejects_untrusted_context(tmp_path):
    _, outcomes = _store(tmp_path)
    with pytest.raises(PermissionError):
        outcomes.list_outcomes({"tenant_id": "tenant-a", "subject_id": "alice"})


def test_outcome_store_rejects_tampered_noncanonical_tenant_context(tmp_path):
    evidence, outcomes = _store(tmp_path)
    owner = TenantContext("tenant-a", "alice")
    object.__setattr__(owner, "tenant_id", "tenant-a" + chr(127))
    with pytest.raises(PermissionError):
        outcomes.list_outcomes(owner)

