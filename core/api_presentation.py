"""Presentation semantics for the Controlador-trade user interface.

This module keeps visual status semantics separate from broker/execution code.
Colors are stable semantic tokens so a future web/mobile UI can render the
same result consistently.
"""
from dataclasses import dataclass
from enum import Enum

from .models import Signal


class PresentationStatus(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    ANALYSIS = "ANALYSIS"
    RISK = "RISK"
    NEUTRAL = "NEUTRAL"
    REAL_BLOCKED = "REAL_BLOCKED"


@dataclass(frozen=True)
class PresentationToken:
    status: PresentationStatus
    label: str
    color: str
    priority: int
    discreet: bool = False


TOKENS = {
    PresentationStatus.BUY: PresentationToken(PresentationStatus.BUY, "COMPRA", "green", 100),
    PresentationStatus.SELL: PresentationToken(PresentationStatus.SELL, "VENDA", "red", 100),
    PresentationStatus.WAIT: PresentationToken(PresentationStatus.WAIT, "AGUARDAR", "yellow", 100),
    PresentationStatus.ANALYSIS: PresentationToken(PresentationStatus.ANALYSIS, "ANÁLISE / INFORMAÇÃO", "blue", 60),
    PresentationStatus.RISK: PresentationToken(PresentationStatus.RISK, "ATENÇÃO / RISCO", "orange", 90),
    PresentationStatus.NEUTRAL: PresentationToken(PresentationStatus.NEUTRAL, "INFORMAÇÃO GERAL", "gray", 40),
    PresentationStatus.REAL_BLOCKED: PresentationToken(PresentationStatus.REAL_BLOCKED, "REAL BLOQUEADO", "security", 110, True),
}


def presentation_for_signal(signal: Signal) -> PresentationToken:
    """Map a trading signal to its primary UI semantic."""
    mapping = {
        Signal.COMPRA: PresentationStatus.BUY,
        Signal.VENDA: PresentationStatus.SELL,
        Signal.AGUARDAR: PresentationStatus.WAIT,
    }
    return TOKENS[mapping[signal]]


def real_blocked_token() -> PresentationToken:
    """Return the discreet, explicit safety state for live trading."""
    return TOKENS[PresentationStatus.REAL_BLOCKED]
