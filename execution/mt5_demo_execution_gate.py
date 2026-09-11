from __future__ import annotations

from dataclasses import dataclass

from execution.mt5_demo_runtime_preflight import MT5RuntimePreflight


@dataclass(frozen=True)
class MT5DemoExecutionGate:
    allowed: bool
    reason: str


def evaluate_execution_gate(preflight: MT5RuntimePreflight) -> MT5DemoExecutionGate:
    """Fail-closed gate for future MT5 DEMO execution; never sends an order."""
    if not preflight.available:
        return MT5DemoExecutionGate(False, "preflight MT5 DEMO indisponível")
    if not preflight.demo:
        return MT5DemoExecutionGate(False, "conta MT5 não confirmada como DEMO")
    if preflight.bid is None or preflight.ask is None:
        return MT5DemoExecutionGate(False, "cotação incompleta")
    if preflight.bid <= 0 or preflight.ask <= 0 or preflight.ask < preflight.bid:
        return MT5DemoExecutionGate(False, "cotação inválida")
    if preflight.volume_min is None or preflight.volume_step is None:
        return MT5DemoExecutionGate(False, "limites de volume ausentes")
    if preflight.volume_min <= 0 or preflight.volume_step <= 0:
        return MT5DemoExecutionGate(False, "limites de volume inválidos")
    return MT5DemoExecutionGate(True, "MT5 DEMO liberado para próxima camada de execução")
