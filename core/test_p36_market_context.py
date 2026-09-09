from datetime import datetime, timedelta, timezone

import pytest

from core.p36_market_context import MarketContext, MarketContextFeed, NewsImpact, NewsEvent


class FakeNewsProvider:
    def __init__(self, events):
        self.events = events

    def fetch(self):
        return self.events


def event(minutes: int, title: str = "Macro update", symbol: str = "BTCUSD") -> NewsEvent:
    return NewsEvent(
        published_at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes),
        title=title,
        source="TestSource",
        symbols=(symbol,),
        impact=NewsImpact.MEDIUM,
    )


def test_event_normalizes_text_and_symbols_and_is_immutable():
    item = NewsEvent(
        datetime(2026, 9, 9, 12, tzinfo=timezone.utc),
        "  Headline  ",
        " Source ",
        ("btcusd",),
    )
    assert item.title == "Headline"
    assert item.source == "Source"
    assert item.symbols == ("BTCUSD",)
    with pytest.raises((AttributeError, TypeError)):
        item.title = "changed"


def test_event_rejects_naive_datetime_and_empty_fields():
    with pytest.raises(ValueError):
        NewsEvent(datetime(2026, 9, 9, 12), "Headline", "Source")
    with pytest.raises(ValueError):
        NewsEvent(datetime(2026, 9, 9, 12, tzinfo=timezone.utc), " ", "Source")
    with pytest.raises(ValueError):
        NewsEvent(datetime(2026, 9, 9, 12, tzinfo=timezone.utc), "Headline", " ")


def test_feed_sorts_events_deterministically():
    context = MarketContextFeed(FakeNewsProvider([event(20, "B"), event(0, "A"), event(10, "C")])).fetch()
    assert [item.title for item in context.events] == ["A", "C", "B"]
    assert isinstance(context, MarketContext)


def test_feed_rejects_invalid_provider_item():
    with pytest.raises(ValueError, match="invalid news events"):
        MarketContextFeed(FakeNewsProvider(["not an event"])).fetch()


def test_filter_by_symbol_and_inclusive_time_window():
    btc = event(0, symbol="BTCUSD")
    eth = event(10, symbol="ETHUSD")
    btc_later = event(20, symbol="BTCUSD")
    context = MarketContext((btc, eth, btc_later))
    feed = MarketContextFeed(FakeNewsProvider([]))
    result = feed.filter(
        context,
        symbol="btcusd",
        start=btc.published_at,
        end=btc_later.published_at,
    )
    assert result.events == (btc, btc_later)


def test_filter_rejects_invalid_arguments():
    feed = MarketContextFeed(FakeNewsProvider([]))
    context = MarketContext(())
    with pytest.raises(ValueError):
        feed.filter(context, symbol=" ")
    with pytest.raises(ValueError):
        feed.filter(context, start=datetime(2026, 9, 9, 12))
    with pytest.raises(ValueError):
        feed.filter(
            context,
            start=datetime(2026, 9, 9, 13, tzinfo=timezone.utc),
            end=datetime(2026, 9, 9, 12, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError):
        feed.filter("invalid")


def test_filter_does_not_mutate_original_context():
    first = event(0)
    second = event(10)
    context = MarketContext((first, second))
    feed = MarketContextFeed(FakeNewsProvider([]))
    filtered = feed.filter(context, symbol="BTCUSD", end=first.published_at)
    assert filtered.events == (first,)
    assert context.events == (first, second)
