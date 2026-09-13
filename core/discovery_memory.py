from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class DiscoveryMemoryValidationError(ValueError):
    """Raised when discovery evidence is incomplete or unsafe."""


@dataclass(frozen=True)
class DiscoveryMemoryRecord:
    """Evidence record for a discovered relationship.

    This memory stores what was observed and validated. It never grants
    execution, scoring, risk, or trade authority.
    """

    timestamp: datetime
    relationships: tuple[str, ...]
    evidence: tuple[str, ...] = ()
    validation_status: str = "UNVALIDATED"
    operationally_admitted: bool = False
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise DiscoveryMemoryValidationError("timestamp deve ser datetime.")
        if not isinstance(self.relationships, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.relationships
        ):
            raise DiscoveryMemoryValidationError("relationships deve conter textos não vazios.")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.evidence
        ):
            raise DiscoveryMemoryValidationError("evidence deve conter textos não vazios.")
        if not isinstance(self.validation_status, str) or not self.validation_status.strip():
            raise DiscoveryMemoryValidationError("validation_status é obrigatório.")
        if self.execution_authorized:
            raise DiscoveryMemoryValidationError(
                "memória de descoberta não pode conceder autorização de execução."
            )


class DiscoveryMemory:
    """Validated memory for discovery evidence, isolated from trade authority."""

    def __init__(self) -> None:
        self._records: list[DiscoveryMemoryRecord] = []

    def append(self, record: DiscoveryMemoryRecord) -> None:
        if not isinstance(record, DiscoveryMemoryRecord):
            raise TypeError("record deve ser DiscoveryMemoryRecord.")
        if self._records and record.timestamp < self._records[-1].timestamp:
            raise DiscoveryMemoryValidationError("registros devem ser cronológicos.")
        self._records.append(record)

    def records(self) -> tuple[DiscoveryMemoryRecord, ...]:
        return tuple(self._records)

    def admitted(self) -> tuple[DiscoveryMemoryRecord, ...]:
        return tuple(r for r in self._records if r.operationally_admitted)

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self._records),
            "admitted": sum(r.operationally_admitted for r in self._records),
            "execution_authorized": sum(r.execution_authorized for r in self._records),
        }
