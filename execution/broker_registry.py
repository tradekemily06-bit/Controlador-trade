from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Mapping

from execution.ports import BrokerAdapter


class BrokerRegistryError(ValueError):
    """Raised when a broker adapter registration is invalid."""


@dataclass(frozen=True)
class BrokerAdapterInfo:
    name: str
    available: bool


class BrokerRegistry:
    """Explicit registry for broker adapters, isolated from decision logic."""

    def __init__(self) -> None:
        self._adapters: dict[str, BrokerAdapter] = {}
        self._lock = RLock()

    def register(self, name: str, adapter: BrokerAdapter) -> None:
        normalized = self._normalize_name(name)
        if not callable(getattr(adapter, "execute", None)):
            raise BrokerRegistryError("adapter deve implementar execute().")
        if not callable(getattr(adapter, "is_available", None)):
            raise BrokerRegistryError("adapter deve implementar is_available().")
        with self._lock:
            if normalized in self._adapters:
                raise BrokerRegistryError(f"adapter já registrado: {normalized}")
            self._adapters[normalized] = adapter

    def get(self, name: str) -> BrokerAdapter:
        normalized = self._normalize_name(name)
        with self._lock:
            try:
                return self._adapters[normalized]
            except KeyError as exc:
                raise BrokerRegistryError(f"adapter não registrado: {normalized}") from exc

    def is_available(self, name: str) -> bool:
        adapter = self.get(name)
        available = adapter.is_available()
        if type(available) is not bool:
            raise BrokerRegistryError("adapter retornou disponibilidade inválida.")
        return available

    def info(self) -> tuple[BrokerAdapterInfo, ...]:
        with self._lock:
            snapshot = tuple(self._adapters.items())
        records = []
        for name, adapter in snapshot:
            available = adapter.is_available()
            if type(available) is not bool:
                raise BrokerRegistryError("adapter retornou disponibilidade inválida.")
            records.append(BrokerAdapterInfo(name=name, available=available))
        return tuple(records)

    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._adapters)

    def as_mapping(self) -> Mapping[str, BrokerAdapter]:
        with self._lock:
            return dict(self._adapters)

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise BrokerRegistryError("nome do adapter não pode ser vazio.")
        return name.strip().lower()
