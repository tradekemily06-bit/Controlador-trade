from datetime import datetime, timezone

import pytest

from core.p36_market_context import MarketContext, NewsEvent, NewsImpact
from core.p37_market_context import ImpactCounts, MarketContextAggregator


BASE = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)


def make_event(title, symbols, impact=NewsImpact.UNKNOWN):
    return NewsEvent(BASE, title, "Source", tuple(symbols), impact)


def test_aggregate_groups_events_and_preserves_declared_impact():
    context = MarketContext(
        (
            make_event("BTC high", ("BTCUSD",), NewsImpact.HIGH),
            make_event("BTC low", ("BTCUSD",), NewsImpact.LOW),
            make_event("ETH medium", ("ETHUSD",), NewsImpact.MEDIUM),
            make_event("Both unknown", ("BTCUSD", "ETHUSD")),
        )
    )
    snapshot = MarketContextAggregator().aggregate(context)

    assert [item.symbol for item in snapshot.symbols] == ["BTCUSD", "ETHUSD"]
    btc, eth = snapshot.symbols
    assert btc.event_count == 3
    assert btc.impact_counts == ImpactCounts(low=1, medium=0, high=1, unknown=1)
    assert eth.event_count == 2
    assert eth.impact_counts == ImpactCounts(low=0, medium=1, high=0, unknown=1)


def test_requested_symbols_are_normalized_and_order_is_explicit():
    context = MarketContext((make_event("BTC", ("BTCUSD",)),))
    snapshot = MarketContextAggregator().aggregate(context, symbols=("ethusd", "btcusd"))

    assert [item.symbol for item in snapshot.symbols] == ["ETHUSD", "BTCUSD"]
    assert snapshot.symbols[0].event_count == 0
    assert snapshot.symbols[1].event_count == 1


def test_events_remain_deterministically_ordered_from_p36_context():
    first = make_event("A", ("BTCUSD",))
    second = make_event("B", ("BTCUSD",))
    context = MarketContext((second, first))
    snapshot = MarketContextAggregator().aggregate(context)

    # Aggregator does not silently reorder or rewrite an already supplied context.
    assert snapshot.symbols[0].events == (second, first)


def test_invalid_context_and_symbols_fail_closed():
    aggregator = MarketContextAggregator()
    with pytest.raises(ValueError):
        aggregator.aggregate("invalid")
    with pytest.raises(ValueError):
        aggregator.aggregate(MarketContext(()), symbols=(" ",))
    with pytest.raises(ValueError):
        aggregator.aggregate(MarketContext(()), symbols=("BTCUSD", "btcusd"))
    with pytest.raises(ValueError):
        aggregator.aggregate(MarketContext(()), symbols=["BTCUSD"])


def test_empty_context_produces_empty_snapshot():
    snapshot = MarketContextAggregator().aggregate(MarketContext(()))
    assert snapshot.symbols == ()


def test_snapshot_and_nested_results_are_immutable():
    event = make_event("BTC", ("BTCUSD",), NewsImpact.HIGH)
    snapshot = MarketContextAggregator().aggregate(MarketContext((event,)))

    with pytest.raises((AttributeError, TypeError)):
        snapshot.symbols = ()
    with pytest.raises((AttributeError, TypeError)):
        snapshot.symbols[0].symbol = "ETHUSD"
