from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.mt5_read_reconciler import (
    MT5HistoryCandidate,
    MT5ReadOnlyReconciler,
    MT5ReconciliationIdentity,
)
from execution.real_reconciliation import ExternalIdentityKind, ReconciliationOutcome


def _identity():
    return MT5ReconciliationIdentity(
        request_id="req-1",
        symbol="EURUSD",
        side="BUY",
        amount=0.10,
        correlation="CTD-abc",
        magic=2609001,
    )


def _raw(kind="DEAL", ticket=123):
    return SimpleNamespace(
        external_id_kind=kind,
        ticket=ticket,
        symbol="EURUSD",
        side="BUY",
        volume=0.10,
        comment="CTD-abc",
        magic=2609001,
        observed_at=datetime.now(timezone.utc),
    )


def _reconciler(deals, orders):
    return MT5ReadOnlyReconciler(
        adapter=ICMarketsMT5DemoAdapter(),
        account_id="123",
        deals_query=lambda **kwargs: deals,
        orders_query=lambda **kwargs: orders,
    )


def test_mt5_resolver_accepts_exactly_one_deal():
    obs = _reconciler([_raw()], []).resolve(_identity())
    assert obs.effective_outcome is ReconciliationOutcome.EXECUTED
    assert obs.external_id == "123"
    assert obs.external_id_kind is ExternalIdentityKind.DEAL


def test_mt5_resolver_rejects_multiple_distinct_deals_as_ambiguous():
    obs = _reconciler([_raw(ticket=123), _raw(ticket=456)], []).resolve(_identity(), reserved_at=datetime.now(timezone.utc))
    assert obs.effective_outcome is ReconciliationOutcome.AMBIGUOUS
    assert obs.external_id is None


def test_mt5_resolver_does_not_treat_order_alone_as_execution():
    obs = _reconciler([], [_raw(kind="ORDER", ticket=99)]).resolve(_identity(), reserved_at=datetime.now(timezone.utc))
    assert obs.effective_outcome is ReconciliationOutcome.NOT_VISIBLE_YET
    assert obs.external_id is None


def test_mt5_resolver_returns_not_found_without_matching_candidates():
    wrong = SimpleNamespace(
        external_id_kind="DEAL", ticket=1, symbol="GBPUSD", side="BUY",
        volume=0.10, comment="CTD-other", magic=2609001,
        observed_at=datetime.now(timezone.utc),
    )
    obs = _reconciler([wrong], []).resolve(_identity(), reserved_at=datetime.now(timezone.utc))
    assert obs.effective_outcome is ReconciliationOutcome.NOT_FOUND


def test_mt5_resolver_fails_closed_when_query_raises():
    r = MT5ReadOnlyReconciler(
        adapter=ICMarketsMT5DemoAdapter(),
        account_id="123",
        deals_query=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("terminal down")),
        orders_query=lambda **kwargs: [],
    )
    obs = r.resolve(_identity(), reserved_at=datetime.now(timezone.utc))
    assert obs.effective_outcome is ReconciliationOutcome.QUERY_FAILED


def test_mt5_resolver_does_not_merge_distinct_deals_by_shared_order():
    a = _raw(ticket=123)
    b = _raw(ticket=456)
    a.order_ticket = b.order_ticket = "same-order"
    obs = _reconciler([a, b], []).resolve(_identity(), reserved_at=datetime.now(timezone.utc))
    assert obs.effective_outcome is ReconciliationOutcome.AMBIGUOUS


def test_mt5_resolver_requires_timezone_aware_reservation_anchor():
    obs = _reconciler([_raw()], []).resolve(_identity())
    assert obs.effective_outcome is ReconciliationOutcome.QUERY_FAILED


def test_mt5_resolver_passes_bounded_time_window_to_queries():
    seen = {}
    def deals(**kwargs):
        seen["deals"] = kwargs
        return []
    def orders(**kwargs):
        seen["orders"] = kwargs
        return []
    anchor = datetime.now(timezone.utc)
    obs = MT5ReadOnlyReconciler(
        adapter=ICMarketsMT5DemoAdapter(),
        account_id="123",
        deals_query=deals,
        orders_query=orders,
    ).resolve(_identity(), reserved_at=anchor)
    assert obs.effective_outcome is ReconciliationOutcome.NOT_FOUND
    assert seen["deals"]["date_from"] < anchor
    assert seen["deals"]["date_to"] > anchor
    assert seen["orders"]["date_from"] == seen["deals"]["date_from"]
    assert seen["orders"]["date_to"] == seen["deals"]["date_to"]
