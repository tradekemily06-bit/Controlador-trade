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
    account_id: str | None = None
    session_id: str | None = None


class BrokerSessionPort(Protocol):
    """Adapter-owned session/authentication check; secrets stay outside the core."""

    def check_session(self) -> BrokerSessionObservation:
        ...


class BrokerSessionBoundary:
    """Read-only session admission; only AUTHENTICATED + bound identity is usable."""

    @staticmethod
    def validate(observation: BrokerSessionObservation) -> BrokerSessionObservation:
        if not isinstance(observation, BrokerSessionObservation):
            raise ValueError("observação de sessão inválida")
        if not isinstance(observation.status, BrokerSessionStatus):
            raise ValueError("status de sessão inválido")
        if not isinstance(observation.message, str) or not observation.message.strip():
            raise ValueError("mensagem de sessão inválida")
        if observation.account_id is not None and (
            not isinstance(observation.account_id, str) or not observation.account_id.strip()
        ):
            raise ValueError("account_id de sessão inválido")
        if observation.session_id is not None and (
            not isinstance(observation.session_id, str) or not observation.session_id.strip()
        ):
            raise ValueError("session_id de sessão inválido")
        if observation.status is BrokerSessionStatus.AUTHENTICATED and (
            not observation.account_id or not observation.session_id
        ):
            raise ValueError("sessão autenticada exige account_id e session_id")
        return observation

    @classmethod
    def is_usable(cls, observation: BrokerSessionObservation) -> bool:
        validated = cls.validate(observation)
        return (
            validated.status is BrokerSessionStatus.AUTHENTICATED
            and bool(validated.account_id)
            and bool(validated.session_id)
        )
