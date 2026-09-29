from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from execution.external_outcome_port import ExternalOutcomePort


class OutcomeRegistryError(ValueError):
    """Raised when an external outcome adapter is invalid or unavailable."""


@dataclass(frozen=True)
class OutcomeAdapterInfo:
    name: str


class ExternalOutcomeRegistry:
    """Provider-neutral registry for close/result adapters.

    Keys are opaque integration identifiers. The registry has no finite broker,
    platform, or transport list and never imports a concrete provider.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ExternalOutcomePort] = {}

    def register(self, name: str, adapter: ExternalOutcomePort) -> None:
        normalized = self._normalize_name(name)
        if normalized in self._adapters:
            raise OutcomeRegistryError(f"outcome adapter já registrado: {normalized}")
        if not callable(getattr(adapter, "close_and_observe", None)):
            raise OutcomeRegistryError("outcome adapter deve implementar close_and_observe().")
        if not callable(getattr(adapter, "observe_closed_position", None)):
            raise OutcomeRegistryError("outcome adapter deve implementar observe_closed_position().")
        self._adapters[normalized] = adapter

    def get(self, name: str) -> ExternalOutcomePort:
        normalized = self._normalize_name(name)
        try:
            return self._adapters[normalized]
        except KeyError as exc:
            raise OutcomeRegistryError(f"outcome adapter não registrado: {normalized}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def info(self) -> tuple[OutcomeAdapterInfo, ...]:
        return tuple(OutcomeAdapterInfo(name) for name in self._adapters)

    def as_mapping(self) -> Mapping[str, ExternalOutcomePort]:
        return dict(self._adapters)

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise OutcomeRegistryError("nome do outcome adapter não pode ser vazio.")
        return name.strip().lower()
