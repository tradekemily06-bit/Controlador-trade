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
    adapter_id: str


# Deliberately module-private capability. Only the broker gateway imports it;
# registry callers receive metadata, never the executable adapter object.
_BROKER_GATEWAY_CAPABILITY = object()


class BrokerRegistry:
    """Explicit broker registry whose executable adapters stay behind the gateway."""

    def __init__(self) -> None:
        self._adapters: dict[str, BrokerAdapter] = {}
        self._adapter_ids: dict[str, str] = {}
        self._lock = RLock()

    def register(self, name: str, adapter: BrokerAdapter, *, adapter_id: str | None = None) -> None:
        normalized = self._normalize_name(name)
        if not callable(getattr(adapter, "execute", None)):
            raise BrokerRegistryError("adapter deve implementar execute().")
        if not callable(getattr(adapter, "is_available", None)):
            raise BrokerRegistryError("adapter deve implementar is_available().")
        if adapter_id is None:
            candidate = getattr(adapter, "adapter_id", None)
            if isinstance(candidate, str) and candidate.strip():
                adapter_id = candidate
            else:
                adapter_id = f"{type(adapter).__module__}.{type(adapter).__qualname__}"
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise BrokerRegistryError("adapter_id não pode ser vazio.")
        normalized_adapter_id = adapter_id.strip()
        with self._lock:
            if normalized in self._adapters:
                raise BrokerRegistryError(f"adapter já registrado: {normalized}")
            if normalized_adapter_id in self._adapter_ids.values():
                raise BrokerRegistryError(f"adapter_id já registrado: {normalized_adapter_id}")
            self._adapters[normalized] = adapter
            self._adapter_ids[normalized] = normalized_adapter_id

    def _get_for_gateway(self, name: str, *, capability: object) -> BrokerAdapter:
        if capability is not _BROKER_GATEWAY_CAPABILITY:
            raise BrokerRegistryError("acesso ao adapter exige a barreira do broker gateway")
        normalized = self._normalize_name(name)
        with self._lock:
            try:
                return self._adapters[normalized]
            except KeyError as exc:
                raise BrokerRegistryError(f"adapter não registrado: {normalized}") from exc

    def adapter_id(self, name: str) -> str:
        """Return immutable adapter identity metadata without exposing the adapter."""
        normalized = self._normalize_name(name)
        with self._lock:
            try:
                return self._adapter_ids[normalized]
            except KeyError as exc:
                raise BrokerRegistryError(f"adapter não registrado: {normalized}") from exc

    def is_available(self, name: str) -> bool:
        normalized = self._normalize_name(name)
        with self._lock:
            adapter = self._adapters.get(normalized)
        if adapter is None:
            raise BrokerRegistryError(f"adapter não registrado: {normalized}")
        return bool(adapter.is_available())

    def info(self) -> tuple[BrokerAdapterInfo, ...]:
        with self._lock:
            adapters = tuple(self._adapters.items())
            ids = dict(self._adapter_ids)
        return tuple(
            BrokerAdapterInfo(
                name=name,
                available=bool(adapter.is_available()),
                adapter_id=ids[name],
            )
            for name, adapter in adapters
        )

    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._adapters)

    def as_mapping(self) -> Mapping[str, BrokerAdapterInfo]:
        """Return metadata only; executable adapters never leave the registry."""
        with self._lock:
            adapters = tuple(self._adapters.items())
            ids = dict(self._adapter_ids)
        return {
            name: BrokerAdapterInfo(
                name=name,
                available=bool(adapter.is_available()),
                adapter_id=ids[name],
            )
            for name, adapter in adapters
        }

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise BrokerRegistryError("nome do adapter não pode ser vazio.")
        return name.strip().lower()
