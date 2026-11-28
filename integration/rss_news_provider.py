from __future__ import annotations

import ipaddress
import os
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from analysis.news_event_intelligence import classify_market_news


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    published_at: str | None = None
    url: str | None = None


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
        opener: Callable = urlopen,
    ) -> None:
        if not feed_urls:
            raise ValueError("ao menos uma URL de feed deve ser configurada")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo")
        self.feed_urls = tuple(self._validate_url(url) for url in feed_urls)
        self.timeout_seconds = timeout_seconds
        self._opener = opener
        self._last_status = {"configured": True, "live": False, "feed_count": len(self.feed_urls), "last_error": None}

    @classmethod
    def _validate_url(cls, value: str) -> str:
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError("URL de feed inválida")
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            raise ValueError("feeds devem usar HTTPS e não podem conter credenciais")
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

    def _fetch_feed(self, url: str) -> list[NewsItem]:
        request = Request(url, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml", "User-Agent": "ControladorTradeNews/1.0"})
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
            if link and not link.startswith("https://"):
                link = None
            published = (
                self._text(entry.find("pubDate"))
                or self._text(entry.find("published"))
                or self._text(entry.find("updated"))
                or self._text(entry.find("{http://www.w3.org/2005/Atom}published"))
                or self._text(entry.find("{http://www.w3.org/2005/Atom}updated"))
            )
            source = self._text(entry.find("source")) or feed_title or host
            items.append(NewsItem(title, source, self._published(published), link))
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
