from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Signal(str, Enum):
    COMPRA = "COMPRA"
    VENDA = "VENDA"
    AGUARDAR = "AGUARDAR"


@dataclass
class AnalysisResult:
    signal: Signal
    score: float
    reason: str
    confirmed: bool = False
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    # None means the analysis source did not explicitly report filter status.
    # This is explanatory metadata only; it never authorizes execution.
    filters_ok: Optional[bool] = None
