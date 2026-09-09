from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class BrokerSessionStatus(str, Enum):
    AUTHENTICATED = "AUTHENTICATED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BrokerSessionObservation:
    status: BrokerSessionStatus
    message: str


class BrokerSessionPort(Protocol):
    """Adapter-owned session/authentication check; secrets stay outside the core."""

    def check_session(self) -> BrokerSessionObservation:
        ...


class BrokerSessionBoundary:
    """Read-only session admission; only AUTHENTICATED is usable."""

    @staticmethod
    def validate(observation: BrokerSessionObservation) -> BrokerSessionObservation:
        if not isinstance(observation, BrokerSessionObservation):
            raise ValueError("observação de sessão inválida")
        if not isinstance(observation.status, BrokerSessionStatus):
            raise ValueError("status de sessão inválido")
        if not isinstance(observation.message, str) or not observation.message.strip():
            raise ValueError("mensagem de sessão inválida")
        return observation

    @classmethod
    def is_usable(cls, observation: BrokerSessionObservation) -> bool:
        validated = cls.validate(observation)
        return validated.status is BrokerSessionStatus.AUTHENTICATED
