"""Trading-psychology guardrails for learning and self-awareness.

Psychology is an educational and behavioral-safety layer. It never diagnoses
mental-health conditions and never authorizes or rejects an order by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PsychologyFlag(str, Enum):
    CLEAR = "CLEAR"
    FOMO = "FOMO"
    REVENGE = "REVENGE"
    OVERCONFIDENCE = "OVERCONFIDENCE"
    FEAR = "FEAR"
    FATIGUE = "FATIGUE"
    TILT = "TILT"


@dataclass(frozen=True)
class PsychologyCheckIn:
    emotional_state: str
    urge_to_trade: int
    recent_losses: int
    fatigue: int
    confidence: int
    rule_adherence: int


@dataclass(frozen=True)
class PsychologyAssessment:
    flags: tuple[PsychologyFlag, ...]
    risk_level: str
    message: str
    suggested_action: str
    trading_authorized: bool = False


class TradingPsychologyGuard:
    """Conservative behavioral feedback; never grants trading permission."""

    def assess(self, check_in: PsychologyCheckIn) -> PsychologyAssessment:
        values = (check_in.urge_to_trade, check_in.fatigue, check_in.confidence, check_in.rule_adherence)
        if any(not isinstance(value, int) or value < 0 or value > 10 for value in values) or check_in.recent_losses < 0:
            raise ValueError("psychology scores must be integers from 0 to 10")

        flags: list[PsychologyFlag] = []
        if check_in.recent_losses >= 2 and check_in.urge_to_trade >= 7:
            flags.append(PsychologyFlag.REVENGE)
        if check_in.urge_to_trade >= 8:
            flags.append(PsychologyFlag.FOMO)
        if check_in.confidence >= 9 and check_in.rule_adherence <= 5:
            flags.append(PsychologyFlag.OVERCONFIDENCE)
        if check_in.fatigue >= 7:
            flags.append(PsychologyFlag.FATIGUE)
        if check_in.rule_adherence <= 4:
            flags.append(PsychologyFlag.TILT)
        if check_in.emotional_state.strip().lower() in {"medo", "fear", "ansioso", "ansiedade"}:
            flags.append(PsychologyFlag.FEAR)

        if flags:
            risk_level = "HIGH" if len(flags) >= 2 else "MODERATE"
            action = "pausar e revisar as regras antes de qualquer operação"
            message = "Sinais comportamentais detectados; o ecossistema não transforma emoção em sinal de entrada."
        else:
            risk_level = "LOW"
            action = "seguir o plano e confirmar as regras antes da decisão"
            message = "Nenhum alerta comportamental forte foi detectado neste check-in."
        return PsychologyAssessment(tuple(dict.fromkeys(flags)), risk_level, message, action, False)
