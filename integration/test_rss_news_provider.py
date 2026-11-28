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
<item><title>EURUSD market outlook</title><description>European Central Bank signals an unexpected interest rate decision</description><link>https://www.cnbc.com/story</link><pubDate>Thu, 26 Nov 2026 12:00:00 GMT</pubDate></item>
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
    assert "unexpected interest rate" in items[0].summary
    assert provider.status()["live"] is True


def test_rss_provider_matches_currency_pair_news_through_underlying_asset():
    macro_rss = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Financial News</title>
    <item><title>Federal Reserve signals a rate decision</title><link>https://www.cnbc.com/fed-story</link></item>
    </channel></rss>"""
    provider = RSSNewsProvider(
        ["https://www.cnbc.com/feed"],
        opener=lambda request, timeout: FakeResponse(macro_rss, "https://www.cnbc.com/feed"),
    )

    items = provider.latest(symbol="EURUSD")

    assert len(items) == 1
    assert "Federal Reserve" in items[0].title


def test_rss_provider_rejects_non_https_and_unapproved_domains():
    with pytest.raises(ValueError):
        RSSNewsProvider(["http://www.cnbc.com/feed"])
    with pytest.raises(ValueError):
        RSSNewsProvider(["https://127.0.0.1/feed"])
    with pytest.raises(ValueError):
        RSSNewsProvider(["https://attacker.example/feed"])


def test_rss_provider_accepts_official_brazilian_primary_sources():
    provider = RSSNewsProvider(["https://www.bcb.gov.br/rss/noticias"])
    assert provider.status()["configured"] is True
    assert provider.status()["feed_count"] == 1


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



@pytest.mark.parametrize("url", [
    "https://www.cnbc.com:8443/feed",
    "https://www.cnbc.com:0/feed",
    "https://www.cnbc.com/feed#fragment",
    "https://user@www.cnbc.com/feed",
])
def test_rss_provider_rejects_nonstandard_or_ambiguous_urls(url):
    with pytest.raises(ValueError):
        RSSNewsProvider([url])


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -float("inf"), 0, -1, 31, True])
def test_rss_provider_rejects_nonfinite_or_unbounded_timeout(timeout):
    with pytest.raises(ValueError):
        RSSNewsProvider(["https://www.cnbc.com/feed"], timeout_seconds=timeout)


def test_default_http_client_rejects_redirects_before_following_them():
    from urllib.error import HTTPError

    from integration.rss_news_provider import _RejectRedirectHandler

    handler = _RejectRedirectHandler()
    request = __import__("urllib.request", fromlist=["Request"]).Request(
        "https://www.cnbc.com/feed"
    )
    with pytest.raises(HTTPError, match="redirects are disabled"):
        handler.redirect_request(
            request,
            object(),
            302,
            "Found",
            {},
            "https://attacker.example/collect",
        )



def test_rss_provider_drops_article_links_outside_the_trusted_publisher_allowlist():
    malicious_link_feed = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Financial News</title>
    <item><title>EURUSD market outlook</title><link>https://attacker.example/collect</link></item>
    </channel></rss>"""
    provider = RSSNewsProvider(
        ["https://www.cnbc.com/feed"],
        opener=lambda request, timeout: FakeResponse(
            malicious_link_feed, "https://www.cnbc.com/feed"
        ),
    )

    items = provider.latest(symbol="EURUSD")

    assert len(items) == 1
    assert items[0].url is None
    assert provider.status()["live"] is True


def _dns_answer(address):
    import socket
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (address, 443))


def test_default_rss_transport_resolves_and_pins_only_public_addresses():
    provider = RSSNewsProvider(
        ["https://www.cnbc.com/feed"],
        resolver=lambda host, port, type: [
            _dns_answer("1.1.1.1"),
            _dns_answer("2606:4700:4700::1111"),
            _dns_answer("1.1.1.1"),
        ],
    )

    assert provider._resolve_public_addresses("www.cnbc.com") == (
        "1.1.1.1",
        "2606:4700:4700::1111",
    )


@pytest.mark.parametrize("addresses", [
    ["127.0.0.1"],
    ["10.0.0.4"],
    ["1.1.1.1", "192.168.1.10"],
    ["169.254.169.254"],
])
def test_default_rss_transport_rejects_private_or_mixed_dns_answers(addresses):
    provider = RSSNewsProvider(
        ["https://www.cnbc.com/feed"],
        resolver=lambda host, port, type: [_dns_answer(address) for address in addresses],
    )

    with pytest.raises(ValueError, match="non-public"):
        provider._resolve_public_addresses("www.cnbc.com")


def test_default_rss_transport_rejects_empty_or_failed_dns_resolution():
    empty = RSSNewsProvider(
        ["https://www.cnbc.com/feed"],
        resolver=lambda host, port, type: [],
    )
    with pytest.raises(ValueError, match="no usable addresses"):
        empty._resolve_public_addresses("www.cnbc.com")

    def failed(host, port, type):
        import socket
        raise socket.gaierror("temporary DNS failure")

    unavailable = RSSNewsProvider(["https://www.cnbc.com/feed"], resolver=failed)
    with pytest.raises(ValueError, match="DNS resolution failed"):
        unavailable._resolve_public_addresses("www.cnbc.com")


def test_pinned_https_connection_connects_to_ip_but_keeps_original_tls_hostname(monkeypatch):
    import socket

    from integration.rss_news_provider import _PinnedHTTPSConnection

    calls = {}

    class FakeSocket:
        def close(self):
            calls["closed"] = True

    class FakeContext:
        def wrap_socket(self, raw_socket, *, server_hostname):
            calls["server_hostname"] = server_hostname
            return raw_socket

    def fake_create_connection(address, timeout, source_address):
        calls["address"] = address
        calls["timeout"] = timeout
        return FakeSocket()

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    connection = _PinnedHTTPSConnection(
        "www.cnbc.com",
        "1.1.1.1",
        timeout=4.0,
        context=FakeContext(),
    )

    connection.connect()

    assert calls["address"] == ("1.1.1.1", 443)
    assert calls["server_hostname"] == "www.cnbc.com"
    assert calls["timeout"] == 4.0
    assert connection.sock is not None
    connection.close()
