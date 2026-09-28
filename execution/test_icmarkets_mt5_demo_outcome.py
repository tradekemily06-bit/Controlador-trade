from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from core.operation_lineage import OperationLineage, OperationLineageStore
from execution.icmarkets_mt5_demo_outcome import ICMarketsMT5DemoOutcomeBridge


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_ENTRY_OUT_BY = 3

    def __init__(self, *, remaining=False, magic=2609001, close_remaining=False):
        self.remaining = remaining
        self.close_remaining = close_remaining
        self.magic = magic
        self.sent_payload = None
        self.shutdown_called = False

    def initialize(self):
        return True

    def shutdown(self):
        self.shutdown_called = True

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO)

    def history_deals_get(self, **kwargs):
        if "ticket" in kwargs:
            return (SimpleNamespace(position_id=123, ticket=501),)
        return (
            SimpleNamespace(
                ticket=601,
                order=701,
                position_id=123,
                entry=self.DEAL_ENTRY_IN,
                time_msc=1000,
                profit=0.0,
                swap=0.0,
                commission=-0.5,
                fee=0.0,
            ),
            SimpleNamespace(
                ticket=602,
                order=702,
                position_id=123,
                entry=self.DEAL_ENTRY_OUT,
                time_msc=2000,
                profit=12.0,
                swap=-0.5,
                commission=-1.0,
                fee=-0.2,
            ),
        )

    def history_orders_get(self, **kwargs):
        return ()

    def positions_get(self, ticket=None):
        if self.remaining:
            return (SimpleNamespace(ticket=123, symbol="EURUSD", volume=0.05, type=self.ORDER_TYPE_BUY, magic=self.magic),)
        return ()

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=1.0990, ask=1.1000)

    def order_check(self, payload):
        return SimpleNamespace(retcode=0)

    def order_send(self, payload):
        self.sent_payload = payload
        self.remaining = self.close_remaining
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=900, deal=901)

    def last_error(self):
        return (0, "ok")


def lineage(store):
    store.put(
        OperationLineage(
            decision_id="decision-1",
            cycle_id="cycle-1",
            request_id="request-1",
            external_id="500",
        )
    )


def test_close_resolves_position_closes_and_builds_factual_result(tmp_path):
    store = OperationLineageStore(tmp_path / "lineage.json")
    lineage(store)
    mt5 = FakeMT5(remaining=True)
    bridge = ICMarketsMT5DemoOutcomeBridge(lineage=store, mt5_module=mt5)

    result = bridge.close_and_observe(
        "request-1",
        now=datetime.now(timezone.utc),
    )

    assert result.position_closed is True
    assert result.outcome_evidence is not None
    assert result.outcome_evidence.external_container_id == "123"
    assert result.outcome_evidence.external_result_ids == ("602",)
    assert result.outcome_evidence.financial_result == pytest.approx(10.3)
    assert result.outcome_evidence.outcome == "WIN"
    assert result.outcome_evidence.as_observation().cycle_id == "cycle-1"
    assert result.outcome_evidence.as_observation().financial_result == pytest.approx(10.3)
    assert mt5.sent_payload["position"] == 123
    assert mt5.sent_payload["type"] == mt5.ORDER_TYPE_SELL

    stored = store.get("request-1")
    assert stored.external_container_id == "123"
    assert stored.external_close_id == "900"
    assert stored.external_result_ids == ("602",)
    assert mt5.shutdown_called is True


def test_partial_close_does_not_create_financial_outcome(tmp_path):
    store = OperationLineageStore(tmp_path / "lineage.json")
    lineage(store)
    mt5 = FakeMT5(remaining=True, close_remaining=True)
    bridge = ICMarketsMT5DemoOutcomeBridge(lineage=store, mt5_module=mt5)

    result = bridge.close_and_observe("request-1")

    assert result.position_closed is False
    assert result.outcome_evidence is None
    assert store.get("request-1").external_close_id == "900"
    assert store.get("request-1").external_result_ids == ()


def test_foreign_magic_position_is_never_closed(tmp_path):
    store = OperationLineageStore(tmp_path / "lineage.json")
    lineage(store)
    mt5 = FakeMT5(remaining=True, magic=999999)
    bridge = ICMarketsMT5DemoOutcomeBridge(lineage=store, mt5_module=mt5)

    with pytest.raises(RuntimeError, match="magic"):
        bridge.close_and_observe("request-1")

    assert mt5.sent_payload is None


def test_already_closed_position_can_be_observed_without_sending(tmp_path):
    store = OperationLineageStore(tmp_path / "lineage.json")
    lineage(store)
    store.attach_external_container_id("request-1", "123")
    mt5 = FakeMT5()
    bridge = ICMarketsMT5DemoOutcomeBridge(lineage=store, mt5_module=mt5)

    evidence = bridge.observe_closed_position("request-1")

    assert evidence is not None
    assert evidence.outcome == "WIN"
    assert evidence.financial_result == pytest.approx(10.3)
    assert mt5.sent_payload is None
