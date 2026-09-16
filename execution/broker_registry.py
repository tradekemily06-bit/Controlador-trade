from __future__ import annotations

from dataclasses import dataclass
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

    def register(self, name: str, adapter: BrokerAdapter, *, adapter_id: str | None = None) -> None:
        normalized = self._normalize_name(name)
        if normalized in self._adapters:
            raise BrokerRegistryError(f"adapter já registrado: {normalized}")
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
        if normalized_adapter_id in self._adapter_ids.values():
            raise BrokerRegistryError(f"adapter_id já registrado: {normalized_adapter_id}")
        self._adapters[normalized] = adapter
        self._adapter_ids[normalized] = normalized_adapter_id

    def resolve_for_gateway(self, name: str, *, capability: object) -> BrokerAdapter:
        """Resolve an executable adapter only for the explicit gateway capability."""
        if capability is not _BROKER_GATEWAY_CAPABILITY:
            raise BrokerRegistryError("acesso ao adapter exige a barreira do broker gateway")
        normalized = self._normalize_name(name)
        try:
            return self._adapters[normalized]
        except KeyError as exc:
            raise BrokerRegistryError(f"adapter não registrado: {normalized}") from exc

    def adapter_id(self, name: str) -> str:
        """Return immutable adapter identity metadata without exposing the adapter."""
        normalized = self._normalize_name(name)
        try:
            return self._adapter_ids[normalized]
        except KeyError as exc:
            raise BrokerRegistryError(f"adapter não registrado: {normalized}") from exc

    def is_available(self, name: str) -> bool:
        # Availability is intentionally metadata-only and cannot return the adapter.
        adapter = self.resolve_for_gateway(name, capability=_BROKER_GATEWAY_CAPABILITY)
        return bool(adapter.is_available())

    def info(self) -> tuple[BrokerAdapterInfo, ...]:
        return tuple(
            BrokerAdapterInfo(
                name=name,
                available=bool(adapter.is_available()),
                adapter_id=self._adapter_ids[name],
            )
            for name, adapter in self._adapters.items()
        )

    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def as_mapping(self) -> Mapping[str, BrokerAdapterInfo]:
        """Return metadata only; executable adapters never leave the registry."""
        return {
            name: BrokerAdapterInfo(
                name=name,
                available=bool(adapter.is_available()),
                adapter_id=self._adapter_ids[name],
            )
            for name, adapter in self._adapters.items()
        }

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise BrokerRegistryError("nome do adapter não pode ser vazio.")
        return name.strip().lower()
