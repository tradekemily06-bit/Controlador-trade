from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from execution.ports import BrokerAdapter


class BrokerRegistryError(ValueError):
    """Raised when a broker adapter registration is invalid."""


@dataclass(frozen=True)
class BrokerAdapterInfo:
    name: str
    adapter_id: str
    available: bool


class BrokerRegistry:
    """Explicit registry for broker adapters, isolated from decision logic."""

    def __init__(self) -> None:
        self._adapters: dict[str, BrokerAdapter] = {}
        self._adapter_ids: dict[str, str] = {}

    def register(self, name: str, adapter: BrokerAdapter, *, adapter_id: str | None = None) -> None:
        normalized = self._normalize_name(name)
        if normalized in self._adapters:
            raise BrokerRegistryError(f"adapter já registrado: {normalized}")
        resolved_adapter_id = self._normalize_name(adapter_id or normalized)
        if resolved_adapter_id in self._adapter_ids.values():
            raise BrokerRegistryError(f"adapter_id já registrado: {resolved_adapter_id}")
        if not callable(getattr(adapter, "execute", None)):
            raise BrokerRegistryError("adapter deve implementar execute().")
        if not callable(getattr(adapter, "is_available", None)):
            raise BrokerRegistryError("adapter deve implementar is_available().")
        self._adapters[normalized] = adapter
        self._adapter_ids[normalized] = resolved_adapter_id

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
            BrokerAdapterInfo(name=name, adapter_id=self._adapter_ids[name], available=bool(adapter.is_available()))
            for name, adapter in self._adapters.items()
        )

    def adapter_id(self, name: str) -> str:
        normalized = self._normalize_name(name)
        try:
            return self._adapter_ids[normalized]
        except KeyError as exc:
            raise BrokerRegistryError(f"adapter não registrado: {normalized}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def as_mapping(self) -> Mapping[str, BrokerAdapter]:
        return dict(self._adapters)

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise BrokerRegistryError("nome do adapter não pode ser vazio.")
        return name.strip().lower()
