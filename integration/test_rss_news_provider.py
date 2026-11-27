from __future__ import annotations

import pytest

from integration.rss_news_provider import RSSNewsProvider, UnconfiguredNewsProvider


class FakeResponse:
    def __init__(self, body: bytes, url: str):
        self.body = body
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.body[:limit]


RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Financial News</title>
<item><title>EURUSD market outlook</title><link>https://www.cnbc.com/story</link><pubDate>Thu, 26 Nov 2026 12:00:00 GMT</pubDate></item>
<item><title>Oil prices update</title><link>https://www.cnbc.com/oil</link></item>
</channel></rss>"""


def test_environment_without_feed_urls_is_explicitly_unconfigured(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_NEWS_FEEDS", raising=False)
    provider = RSSNewsProvider.from_environment()
    assert isinstance(provider, UnconfiguredNewsProvider)
    assert provider.latest() == []


def test_rss_provider_parses_feed_filters_symbol_and_reports_live():
    provider = RSSNewsProvider(
        ["https://www.cnbc.com/id/100003114/device/rss/rss.html"],
        opener=lambda request, timeout: FakeResponse(RSS, "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    )

    items = provider.latest(symbol="EURUSD", limit=10)

    assert len(items) == 1
    assert items[0].title == "EURUSD market outlook"
    assert items[0].source == "Financial News"
    assert items[0].published_at is not None
    assert provider.status()["live"] is True


def test_rss_provider_rejects_non_https_and_unapproved_domains():
    with pytest.raises(ValueError):
        RSSNewsProvider(["http://www.cnbc.com/feed"])
    with pytest.raises(ValueError):
        RSSNewsProvider(["https://127.0.0.1/feed"])
    with pytest.raises(ValueError):
        RSSNewsProvider(["https://attacker.example/feed"])


def test_rss_provider_rejects_redirect_to_unapproved_domain():
    provider = RSSNewsProvider(
        ["https://www.cnbc.com/feed"],
        opener=lambda request, timeout: FakeResponse(RSS, "https://attacker.example/feed"),
    )

    assert provider.latest() == []
    assert provider.status()["live"] is False
    assert "domínio" in provider.status()["last_error"]


def test_atom_provider_parses_namespaced_article_link_and_publication():
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Market Wire</title>
      <entry>
        <title>EURUSD outlook</title>
        <link href="https://www.cnbc.com/atom-story" rel="alternate"/>
        <published>2026-11-26T12:00:00Z</published>
      </entry>
    </feed>"""
    provider = RSSNewsProvider(
        ["https://www.cnbc.com/feed.atom"],
        opener=lambda request, timeout: FakeResponse(atom, "https://www.cnbc.com/feed.atom"),
    )

    items = provider.latest(symbol="EURUSD")

    assert len(items) == 1
    assert items[0].url == "https://www.cnbc.com/atom-story"
    assert items[0].source == "Market Wire"
    assert items[0].published_at == "2026-11-26T12:00:00+00:00"
