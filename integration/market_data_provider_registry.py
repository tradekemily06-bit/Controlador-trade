"""Registry for broker-neutral, read-only market-data provider adapters."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RegisteredMarketDataProvider:
    provider_id: str
    source: str
    provider: Any


class MarketDataProviderRegistry:
    """Allow multiple broker/provider adapters without coupling analysis to one broker."""

    def __init__(self) -> None:
        self._providers: dict[str, RegisteredMarketDataProvider] = {}
        self._selected: str | None = None

    @staticmethod
    def _provider_id(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", value):
            raise ValueError("provider_id inválido")
        return value

    def register(self, provider_id: str, provider: Any, source: str) -> None:
        key = self._provider_id(provider_id)
        if provider is None or not callable(getattr(provider, "fetch", None)):
            raise ValueError("provider must implement fetch(request)")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source é obrigatória")
        if key in self._providers:
            raise ValueError("provider_id já registrado")
        self._providers[key] = RegisteredMarketDataProvider(key, source.strip(), provider)
        if self._selected is None and len(self._providers) == 1:
            self._selected = key

    def select(self, provider_id: str) -> RegisteredMarketDataProvider:
        key = self._provider_id(provider_id)
        try:
            provider = self._providers[key]
        except KeyError as exc:
            raise ValueError("provider não registrado") from exc
        self._selected = key
        return provider

    def selected(self) -> RegisteredMarketDataProvider | None:
        return self._providers.get(self._selected) if self._selected else None

    def status(self) -> dict[str, Any]:
        return {
            "selected_provider": self._selected,
            "providers": [
                {
                    "provider_id": item.provider_id,
                    "source": item.source,
                    "status": "REGISTERED_NOT_TESTED",
                    "selected": item.provider_id == self._selected,
                    "read_only": True,
                    "execution_authorized": False,
                }
                for item in self._providers.values()
            ],
            "count": len(self._providers),
            "provider_registered": bool(self._providers),
        }

    @classmethod
    def from_mapping(
        cls,
        providers: Mapping[str, tuple[Any, str]] | None = None,
        *,
        selected_provider: str | None = None,
    ) -> "MarketDataProviderRegistry":
        registry = cls()
        for provider_id, item in (providers or {}).items():
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("cada provider deve ser um par (provider, source)")
            registry.register(provider_id, item[0], item[1])
        if selected_provider:
            registry.select(selected_provider)
        return registry
