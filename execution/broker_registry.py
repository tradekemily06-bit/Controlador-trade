from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from execution.ports import AdapterConnectionIdentity, BrokerAdapter


class BrokerRegistryError(ValueError):
    """Raised when a broker adapter registration is invalid."""


@dataclass(frozen=True)
class BrokerAdapterInfo:
    name: str
    available: bool
    identity: AdapterConnectionIdentity | None = None


class BrokerRegistry:
    """Explicit registry for broker adapters, isolated from decision logic."""

    def __init__(self) -> None:
        self._adapters: dict[str, BrokerAdapter] = {}
        self._identities: dict[str, AdapterConnectionIdentity | None] = {}

    def register(
        self,
        name: str,
        adapter: BrokerAdapter,
        *,
        identity: AdapterConnectionIdentity | None = None,
    ) -> None:
        normalized = self._normalize_name(name)
        if normalized in self._adapters:
            raise BrokerRegistryError(f"adapter já registrado: {normalized}")
        if not callable(getattr(adapter, "execute", None)):
            raise BrokerRegistryError("adapter deve implementar execute().")
        if not callable(getattr(adapter, "is_available", None)):
            raise BrokerRegistryError("adapter deve implementar is_available().")
        self._adapters[normalized] = adapter
        self._identities[normalized] = identity

    def get(self, name: str) -> BrokerAdapter:
        normalized = self._normalize_name(name)
        try:
            return self._adapters[normalized]
        except KeyError as exc:
            raise BrokerRegistryError(f"adapter não registrado: {normalized}") from exc

    def is_available(self, name: str) -> bool:
        adapter = self.get(name)
        return bool(adapter.is_available())

    def info(self) -> tuple[BrokerAdapterInfo, ...]:
        return tuple(
            BrokerAdapterInfo(
                name=name,
                available=bool(adapter.is_available()),
                identity=self._identities.get(name),
            )
            for name, adapter in self._adapters.items()
        )

    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def as_mapping(self) -> Mapping[str, BrokerAdapter]:
        return dict(self._adapters)

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise BrokerRegistryError("nome do adapter não pode ser vazio.")
        return name.strip().lower()
