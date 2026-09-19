from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.demo_risk_state_store import DemoRiskStateStore, DemoRiskStateUnavailable
from core.operational_state import OperationalState


def _state() -> OperationalState:
    return OperationalState(
        balance=1000.0, equity=1000.0, realized_pnl=0.0, unrealized_pnl=0.0,
        trades_today=0, consecutive_losses=0, open_positions=0,
        net_position=0.0, exposure=0.0, market_open=True,
    )


def test_demo_risk_state_rejects_oversized_persisted_file(tmp_path: Path):
    path = tmp_path / "risk.json"
    path.write_bytes(b"{" + b"x" * (DemoRiskStateStore.MAX_FILE_BYTES + 1))
    store = DemoRiskStateStore(path)
    with pytest.raises(DemoRiskStateUnavailable, match="excede o limite"):
        store.current()


def test_demo_risk_state_rejects_symlink(tmp_path: Path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    path = tmp_path / "risk.json"
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink não suportado neste ambiente")
    store = DemoRiskStateStore(path)
    with pytest.raises(DemoRiskStateUnavailable, match="arquivo regular"):
        store.current()


def test_demo_risk_state_write_is_bounded(tmp_path: Path):
    path = tmp_path / "risk.json"
    store = DemoRiskStateStore(path)
    store.MAX_FILE_BYTES = 128
    with pytest.raises(ValueError, match="excede o limite"):
        store.replace(_state(), source="reconciliation")
