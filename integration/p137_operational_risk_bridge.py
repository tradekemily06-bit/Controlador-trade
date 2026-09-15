"""Translate explicit application/runtime risk state into the operational risk gate.

The bridge validates the boundary, builds OperationalState, delegates policy to
RiskManager, and optionally reconciles a calculated leverage assessment with
the same operation's operational exposure. It never grants execution authority.

Operational approval is fail-closed against the global runtime barrier and, for
an operationally bound bridge, against missing authoritative risk state. A
caller cannot turn an untrusted payload into the account state used for an
operational approval.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Mapping

from core.ecosystem_incidents import EcosystemIncidentManager
from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage
from core.operational_state import OperationalState, OperationalStateValidationError
from core.point_value_engine import PointValueRequest
from core.risk_manager import RiskDecision, RiskManager


def _missing_runtime_barrier() -> GlobalOperationalBarrier:
    """Return a deliberately blocked barrier for unbound operational callers."""
    return GlobalOperationalBarrier(
        components=(
            SafetyComponent(
                name="operational-runtime",
                healthy=False,
                reason="runtime operacional não foi fornecido ao bridge de risco",
            ),
        )
    )


class OperationalRiskBridge:
    """Fail-closed adapter between application payloads and RiskManager."""

    def __init__(
        self,
        risk_manager: RiskManager,
        incident_manager: EcosystemIncidentManager | None = None,
        operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
        operational_state_provider: Callable[[], OperationalState | None] | None = None,
    ) -> None:
        if not isinstance(risk_manager, RiskManager):
            raise ValueError("risk_manager must be RiskManager")
        if incident_manager is not None and not isinstance(incident_manager, EcosystemIncidentManager):
            raise ValueError("incident_manager must be EcosystemIncidentManager")
        if operational_state_provider is not None and not callable(operational_state_provider):
            raise ValueError("operational_state_provider must be callable")
        self.risk_manager = risk_manager
        self.incident_manager = incident_manager
        self._runtime_barrier_bound = operational_barrier_provider is not None
        self.operational_barrier_provider = operational_barrier_provider or _missing_runtime_barrier
        self.operational_state_provider = operational_state_provider

    def _barrier_blocked(self) -> bool:
        try:
            barrier = self.operational_barrier_provider()
            if not isinstance(barrier, GlobalOperationalBarrier):
                return True
            return not barrier.evaluate().operationally_allowed
        except Exception:
            return True

    def _incident_blocked(self) -> bool:
        if self.incident_manager is None:
            return False
        try:
            return self.incident_manager.execution_blocked()
        except (OSError, ValueError, TypeError, RuntimeError):
            return True

    def _operational_blocked(self) -> bool:
        return self._barrier_blocked() or self._incident_blocked()

    def _authoritative_state(self, payload: Mapping[str, Any]) -> OperationalState:
        """Resolve risk state without allowing an operational payload to spoof it."""
        if self._runtime_barrier_bound:
            if self.operational_state_provider is None:
                raise OperationalStateValidationError(
                    "fonte autoritativa de estado de risco não foi fornecida"
                )
            state = self.operational_state_provider()
            if not isinstance(state, OperationalState):
                raise OperationalStateValidationError(
                    "fonte autoritativa de estado de risco indisponível"
                )
            return state
        return self.build_state(payload)

    def evaluate(self, payload: Mapping[str, Any]) -> RiskDecision:
        if self._operational_blocked():
            return RiskDecision(False, "Operação bloqueada: barreira operacional global não está READY.")
        try:
            state = self._authoritative_state(payload)
        except (TypeError, ValueError, OperationalStateValidationError):
            return RiskDecision(False, "Estado operacional de risco não possui fonte autoritativa válida.")

        base = self.risk_manager.evaluate(state=state)
        if not base.allowed:
            return base

        if self._operational_blocked():
            return RiskDecision(False, "Operação bloqueada: barreira operacional detectada durante a avaliação de risco.")

        leverage_decision = self._evaluate_leverage(payload, state)
        if leverage_decision is not None and not leverage_decision.allowed:
            return leverage_decision

        if self._operational_blocked():
            return RiskDecision(False, "Operação bloqueada: barreira operacional mudou antes da conclusão do risco.")
        return base

    @staticmethod
    def build_state(payload: Mapping[str, Any]) -> OperationalState:
        """Parse explicit state for non-operational/test contexts only.

        This helper is intentionally not authoritative when the bridge is bound
        to the operational runtime.
        """
        if not isinstance(payload, Mapping):
            raise ValueError("analysis payload must be an object")
        raw = payload.get("operational_state")
        if not isinstance(raw, Mapping):
            raise ValueError("operational_state is required for risk approval")

        fields = {
            "balance": raw.get("balance"),
            "equity": raw.get("equity"),
            "realized_pnl": raw.get("realized_pnl"),
            "unrealized_pnl": raw.get("unrealized_pnl"),
            "trades_today": raw.get("trades_today"),
            "consecutive_losses": raw.get("consecutive_losses"),
            "open_positions": raw.get("open_positions"),
            "net_position": raw.get("net_position"),
            "exposure": raw.get("exposure"),
            "market_open": raw.get("market_open"),
        }
        timestamp = raw.get("last_processed_candle")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        fields["last_processed_candle"] = timestamp
        return OperationalState(**fields)

    @staticmethod
    def _decimal(value: object, field: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except Exception as exc:
            raise ValueError(f"{field} must be numeric") from exc
        if not result.is_finite():
            raise ValueError(f"{field} must be finite")
        return result

    @classmethod
    def _evaluate_leverage(cls, payload: Mapping[str, Any], state: OperationalState) -> RiskDecision | None:
        raw = payload.get("leverage_request")
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            return RiskDecision(False, "Dados de alavancagem inválidos.")

        required = ("request_id", "profile_id", "symbol", "requested_leverage", "capital_allocated", "quantity", "price")
        if any(key not in raw for key in required):
            return RiskDecision(False, "Dados obrigatórios de alavancagem indisponíveis.")

        point_raw = raw.get("point_value_request")
        point_request = None
        if point_raw is not None:
            if not isinstance(point_raw, Mapping):
                return RiskDecision(False, "Fonte de valor de ponto inválida.")
            point_required = ("instrument", "broker", "account_currency", "quote_currency", "quantity", "price")
            if any(key not in point_raw for key in point_required):
                return RiskDecision(False, "Fonte de valor de ponto incompleta.")
            try:
                point_request = PointValueRequest(
                    instrument=str(point_raw["instrument"]),
                    broker=str(point_raw["broker"]),
                    account_currency=str(point_raw["account_currency"]),
                    quote_currency=str(point_raw["quote_currency"]),
                    quantity=cls._decimal(point_raw["quantity"], "point.quantity"),
                    price=cls._decimal(point_raw["price"], "point.price"),
                    tick_size=cls._decimal(point_raw["tick_size"], "point.tick_size") if point_raw.get("tick_size") is not None else None,
                    tick_value=cls._decimal(point_raw["tick_value"], "point.tick_value") if point_raw.get("tick_value") is not None else None,
                    point_size=cls._decimal(point_raw["point_size"], "point.point_size") if point_raw.get("point_size") is not None else None,
                    contract_size=cls._decimal(point_raw["contract_size"], "point.contract_size") if point_raw.get("contract_size") is not None else None,
                    value_per_price_unit=cls._decimal(point_raw["value_per_price_unit"], "point.value_per_price_unit") if point_raw.get("value_per_price_unit") is not None else None,
                    quote_to_account_rate=cls._decimal(point_raw["quote_to_account_rate"], "point.quote_to_account_rate") if point_raw.get("quote_to_account_rate") is not None else None,
                    as_of=cls._timestamp(point_raw.get("as_of")),
                    now=cls._timestamp(point_raw.get("now")),
                    conversion_max_age_seconds=cls._decimal(point_raw["conversion_max_age_seconds"], "point.conversion_max_age_seconds") if point_raw.get("conversion_max_age_seconds") is not None else None,
                )
            except (TypeError, ValueError) as exc:
                return RiskDecision(False, f"Fonte de valor de ponto inválida: {exc}.")

        try:
            request = LeverageRequest(
                request_id=str(raw["request_id"]),
                profile_id=str(raw["profile_id"]),
                symbol=str(raw["symbol"]),
                requested_leverage=cls._decimal(raw["requested_leverage"], "requested_leverage"),
                capital_allocated=cls._decimal(raw["capital_allocated"], "capital_allocated"),
                quantity=cls._decimal(raw["quantity"], "quantity"),
                price=cls._decimal(raw["price"], "price"),
                stop_distance=cls._decimal(raw["stop_distance"], "stop_distance") if raw.get("stop_distance") is not None else None,
                value_per_price_unit=cls._decimal(raw["value_per_price_unit"], "value_per_price_unit") if raw.get("value_per_price_unit") is not None else None,
                maximum_loss=cls._decimal(raw["maximum_loss"], "maximum_loss") if raw.get("maximum_loss") is not None else None,
                environment=str(raw.get("environment", "DEMO")),
                point_value_request=point_request,
                margin_required=cls._decimal(raw["margin_required"], "margin_required") if raw.get("margin_required") is not None else None,
            )
        except (TypeError, ValueError) as exc:
            return RiskDecision(False, f"Dados de alavancagem inválidos: {exc}.")

        assessment = assess_leverage(request)
        if assessment.status is LeverageStatus.BLOCKED:
            return RiskDecision(False, "Risco da operação excede o orçamento permitido.")
        if assessment.status is LeverageStatus.REASSESS:
            return RiskDecision(False, "Dados de alavancagem/ponto exigem reavaliação antes da aprovação.")

        if state.exposure is not None and assessment.exposure is not None:
            try:
                operational_exposure = cls._decimal(state.exposure, "operational_state.exposure")
            except ValueError:
                return RiskDecision(False, "Exposição operacional inválida.")
            if operational_exposure != assessment.exposure:
                return RiskDecision(False, "Exposição operacional diverge da exposição calculada; reavaliação necessária.")
        elif assessment.exposure is not None:
            return RiskDecision(False, "Exposição operacional ausente para reconciliação.")

        return None

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError("timestamp must be ISO datetime")
