"""Translate explicit application/runtime risk state into the operational risk gate.

The bridge validates the boundary, builds OperationalState, delegates policy to
RiskManager, and optionally reconciles a calculated leverage assessment with
the same operation's operational exposure. It never grants execution authority.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from core.leverage_operation import LeverageRequest, LeverageStatus, assess_leverage
from core.operational_state import OperationalState, OperationalStateValidationError
from core.point_value_engine import PointValueRequest
from core.risk_manager import RiskDecision, RiskManager


class OperationalRiskBridge:
    """Fail-closed adapter between application payloads and RiskManager."""

    def __init__(self, risk_manager: RiskManager) -> None:
        if not isinstance(risk_manager, RiskManager):
            raise ValueError("risk_manager must be RiskManager")
        self.risk_manager = risk_manager

    def evaluate(self, payload: Mapping[str, Any]) -> RiskDecision:
        try:
            state = self.build_state(payload)
        except (TypeError, ValueError, OperationalStateValidationError):
            return RiskDecision(False, "Estado operacional de risco inválido.")

        base = self.risk_manager.evaluate(state=state)
        if not base.allowed:
            return base

        leverage_decision = self._evaluate_leverage(payload, state)
        if leverage_decision is not None and not leverage_decision.allowed:
            return leverage_decision
        return base

    @staticmethod
    def build_state(payload: Mapping[str, Any]) -> OperationalState:
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
