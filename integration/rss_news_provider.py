from __future__ import annotations

import http.client
import ipaddress
import math
import os
import socket
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from analysis.news_event_intelligence import classify_market_news


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    published_at: str | None = None
    url: str | None = None
    summary: str | None = None


class NewsProvider:
    def status(self) -> dict[str, object]:
        return dict(self._last_status)

    def latest(self, *, symbol: str | None = None, limit: int = 10) -> list[NewsItem]:
        raise NotImplementedError


class UnconfiguredNewsProvider(NewsProvider):
    """Fail-closed provider: never fabricates or claims live news."""

    def status(self) -> dict[str, object]:
        return {"configured": False, "live": False, "feed_count": 0, "last_error": None}

    def latest(self, *, symbol: str | None = None, limit: int = 10) -> list[NewsItem]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit deve estar entre 1 e 50")
        return []


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a prevalidated public IP, with normal TLS SNI."""

    def __init__(self, host: str, pinned_ip: str, *, timeout: float, context: ssl.SSLContext):
        super().__init__(host, port=443, timeout=timeout, context=context)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        if self._tunnel_host:
            raise OSError("HTTPS proxy tunnels are not supported for pinned news requests")
        raw_socket = socket.create_connection(
            (self._pinned_ip, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


class _RejectRedirectHandler(HTTPRedirectHandler):
    """Reject redirects before urllib can issue a request to another host."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        raise HTTPError(
            request.full_url,
            code,
            "redirects are disabled for configured news feeds",
            headers,
            None,
        )


class RSSNewsProvider(NewsProvider):
    """Read-only RSS/Atom reader. Feed URLs are explicit server configuration."""

    MAX_FEED_BYTES = 1_000_000
    ALLOWED_DOMAINS = (
        # Reputable financial/news publishers.
        "cnbc.com", "finance.yahoo.com", "marketwatch.com",
        "investing.com", "reuters.com", "apnews.com", "ft.com",
        # Primary sources: central banks, statistical agencies and regulators.
        "federalreserve.gov", "ecb.europa.eu", "bankofengland.co.uk",
        "bankofcanada.ca", "boj.or.jp", "rba.gov.au", "rbnz.govt.nz",
        "snb.ch", "bcb.gov.br", "ibge.gov.br", "bls.gov", "bea.gov",
        "ons.gov.uk", "ec.europa.eu", "imf.org", "worldbank.org",
        "home.treasury.gov", "sec.gov", "cftc.gov",
    )

    def __init__(
        self,
        feed_urls: list[str],
        *,
        timeout_seconds: float = 8.0,
        opener: Callable | None = None,
        resolver: Callable | None = None,
    ) -> None:
        if not feed_urls:
            raise ValueError("ao menos uma URL de feed deve ser configurada")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
            or timeout_seconds > 30
        ):
            raise ValueError("timeout_seconds deve ser finito, positivo e no máximo 30")
        self.feed_urls = tuple(self._validate_url(url) for url in feed_urls)
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener
        self._resolver = resolver or socket.getaddrinfo
        self._last_status = {"configured": True, "live": False, "feed_count": len(self.feed_urls), "last_error": None}

    @classmethod
    def _validate_url(cls, value: str) -> str:
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError("URL de feed inválida")
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("porta da URL de feed inválida") from exc
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or port not in (None, 443)
            or parsed.fragment
        ):
            raise ValueError("feeds devem usar HTTPS na porta padrão e não podem conter credenciais ou fragmentos")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("endereço de feed não público")
        if not any(host == domain or host.endswith("." + domain) for domain in cls.ALLOWED_DOMAINS):
            raise ValueError("domínio de feed não permitido")
        return value.strip()

    @classmethod
    def from_environment(cls) -> RSSNewsProvider | UnconfiguredNewsProvider:
        raw = os.getenv("CONTROLADOR_NEWS_FEEDS", "").strip()
        if not raw:
            return UnconfiguredNewsProvider()
        urls = [item.strip() for item in raw.split(";") if item.strip()]
        return cls(urls)

    @staticmethod
    def _text(element: ET.Element | None) -> str | None:
        if element is None:
            return None
        return " ".join("".join(element.itertext()).split()) or None

    @staticmethod
    def _published(value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            try:
                from datetime import datetime
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                return None

    def _resolve_public_addresses(self, host: str, port: int = 443) -> tuple[str, ...]:
        """Resolve once, reject mixed/private DNS answers, and pin the chosen IP."""
        try:
            answers = self._resolver(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("news feed DNS resolution failed") from exc
        addresses: list[str] = []
        for answer in answers:
            try:
                raw_address = answer[4][0].split("%", 1)[0]
                address = ipaddress.ip_address(raw_address)
            except (IndexError, AttributeError, TypeError, ValueError) as exc:
                raise ValueError("news feed DNS returned an invalid address") from exc
            if not address.is_global:
                raise ValueError("news feed DNS resolved to a non-public address")
            normalized = str(address)
            if normalized not in addresses:
                addresses.append(normalized)
        if not addresses:
            raise ValueError("news feed DNS returned no usable addresses")
        return tuple(addresses)

    def _fetch_pinned_https(self, url: str) -> tuple[str, bytes]:
        """Fetch HTTPS directly to a validated IP while retaining TLS hostname checks."""
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise ValueError("news feed host is missing")
        addresses = self._resolve_public_addresses(host, 443)
        # Do not fall back to a second DNS lookup in the HTTP stack: the
        # connection is pinned to the address validated immediately above.
        connection = _PinnedHTTPSConnection(
            host,
            addresses[0],
            timeout=self.timeout_seconds,
            context=ssl.create_default_context(),
        )
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                    "Accept-Encoding": "identity",
                    "User-Agent": "ControladorTradeNews/1.0",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise ValueError("news feed redirects are disabled")
            if not 200 <= response.status < 300:
                raise ValueError(f"news feed returned HTTP {response.status}")
            content_length = response.getheader("Content-Length")
            if content_length:
                try:
                    if int(content_length) > self.MAX_FEED_BYTES:
                        raise ValueError("feed excede o limite de tamanho")
                except ValueError as exc:
                    if "feed excede" in str(exc):
                        raise
                    raise ValueError("news feed returned invalid content length") from exc
            raw = response.read(self.MAX_FEED_BYTES + 1)
            if len(raw) > self.MAX_FEED_BYTES:
                raise ValueError("feed excede o limite de tamanho")
            return url, raw
        finally:
            connection.close()

    def _fetch_feed(self, url: str) -> list[NewsItem]:
        if self._opener is None:
            final_url, raw = self._fetch_pinned_https(url)
        else:
            request = Request(url, headers={
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                "Accept-Encoding": "identity",
                "User-Agent": "ControladorTradeNews/1.0",
            })
            with self._opener(request, timeout=self.timeout_seconds) as response:
                final_url = self._validate_url(response.geturl())
                raw = response.read(self.MAX_FEED_BYTES + 1)
        if len(raw) > self.MAX_FEED_BYTES:
            raise ValueError("feed excede o limite de tamanho")
        root = ET.fromstring(raw)
        host = urlparse(final_url).hostname or "fonte"
        channel = root.find("./channel")
        feed_title = self._text(channel.find("title")) if channel is not None else self._text(root.find("{http://www.w3.org/2005/Atom}title"))
        items: list[NewsItem] = []
        entries = root.findall(".//item")
        if not entries:
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for entry in entries:
            title = self._text(entry.find("title")) or self._text(entry.find("{http://www.w3.org/2005/Atom}title"))
            if not title:
                continue
            link_element = entry.find("link")
            if link_element is None:
                link_element = entry.find("{http://www.w3.org/2005/Atom}link")
            link = None
            if link_element is not None:
                link = link_element.get("href") or self._text(link_element)
            if link:
                try:
                    link = self._validate_url(link)
                except ValueError:
                    # Feed entries are untrusted content. Keep the headline but
                    # do not surface an arbitrary or deceptive destination.
                    link = None
            published = (
                self._text(entry.find("pubDate"))
                or self._text(entry.find("published"))
                or self._text(entry.find("updated"))
                or self._text(entry.find("{http://www.w3.org/2005/Atom}published"))
                or self._text(entry.find("{http://www.w3.org/2005/Atom}updated"))
            )
            source = self._text(entry.find("source")) or feed_title or host
            summary_element = (
                entry.find("description")
                or entry.find("summary")
                or entry.find("{http://www.w3.org/2005/Atom}summary")
                or entry.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            )
            summary = self._text(summary_element)
            if summary is not None:
                summary = summary[:4000]
            items.append(NewsItem(title, source, self._published(published), link, summary))
        return items

    def latest(self, *, symbol: str | None = None, limit: int = 10) -> list[NewsItem]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit deve estar entre 1 e 50")
        query = symbol.strip().upper() if isinstance(symbol, str) and symbol.strip() else None
        collected: list[NewsItem] = []
        errors: list[str] = []
        successful_feeds = 0
        for url in self.feed_urls:
            try:
                items = self._fetch_feed(url)
            except Exception as exc:
                errors.append(str(exc)[:160])
                continue
            successful_feeds += 1
            for item in items:
                if query and query not in item.title.upper():
                    classified_assets = set(classify_market_news(item)["affected_assets"])
                    components = {query}
                    if len(query) == 6 and query.isalpha():
                        components.update((query[:3], query[3:]))
                    aliases = {"XAU": "GOLD", "XAG": "SILVER"}
                    relevant_assets = {aliases.get(code, code) for code in components}
                    if not relevant_assets.intersection(classified_assets):
                        continue
                collected.append(item)
        unique: dict[tuple[str, str | None], NewsItem] = {}
        for item in collected:
            unique.setdefault((item.title.casefold(), item.url), item)
        self._last_status = {
            "configured": True,
            "live": successful_feeds > 0,
            "feed_count": len(self.feed_urls),
            "successful_feeds": successful_feeds,
            "last_error": "; ".join(errors[:3]) or None,
        }
        ordered = sorted(
            unique.values(),
            key=lambda item: item.published_at or "",
            reverse=True,
        )
        return ordered[:limit]
