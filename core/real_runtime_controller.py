from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from core.real_manual_confirmation import RealManualConfirmationGate
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode, ExecutionRequest
from execution.real_gateway import RealExecutionGateway, RealGatewayResult
from execution.default_registry import IC_MARKETS_MT5_REAL, build_real_registry


class RealRuntimeController:
    """Single runtime boundary for explicit, human-confirmed MT5 REAL execution.

    The controller never enables REAL by default. Every mutation is re-gated
    from current runtime state immediately before dispatch.
    """

    def __init__(self, *, runtime: Any, root: str | Path, symbol: str | None = None) -> None:
        if runtime is None:
            raise ValueError("runtime operacional é obrigatório.")
        self.runtime = runtime
        self.root = Path(root)
        self.symbol = symbol
        self.broker_id = IC_MARKETS_MT5_REAL
        self.registry: BrokerRegistry = build_real_registry(symbol=symbol)
        self.gateway = RealExecutionGateway(
            BrokerAdapterGateway(self.registry),
            self.runtime.execution_ledger,
        )
        self.confirmation = RealManualConfirmationGate(
            ttl_seconds=self._env_int("CONTROLADOR_REAL_CONFIRMATION_TTL", 60, 1, 300)
        )

    @staticmethod
    def _env_bool(name: str, default: bool = False) -> bool:
        value = os.environ.get(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
        value = os.environ.get(name)
        if value is None or not value.strip():
            return default
        parsed = int(value)
        if not minimum <= parsed <= maximum:
            raise ValueError(f"{name} deve estar entre {minimum} e {maximum}.")
        return parsed

    def _authorization(self) -> RealExecutionAuthorization:
        authorization_id = os.environ.get("CONTROLADOR_REAL_AUTHORIZATION_ID", "").strip()
        audit_id = os.environ.get("CONTROLADOR_REAL_AUDIT_ID", "").strip()
        explicitly_enabled = self._env_bool("CONTROLADOR_REAL_EXPLICITLY_ENABLED") and bool(authorization_id)
        real_execution_allowed = self._env_bool("CONTROLADOR_REAL_EXECUTION_ALLOWED") and bool(audit_id)
        return RealExecutionAuthorization(
            authorization_id=authorization_id or "real-disabled",
            audit_id=audit_id or "real-disabled",
            broker_id=self.broker_id,
            adapter_id="ic_markets_mt5_real",
            explicitly_enabled=explicitly_enabled,
            real_execution_allowed=real_execution_allowed,
        )

    def _broker_available(self) -> bool:
        try:
            return self.registry.is_available(self.broker_id)
        except Exception:
            return False

    def _market_healthy(self) -> bool:
        report = getattr(self.runtime.market_data, "report", None)
        return bool(report is not None and report.safe_for_analysis)

    def _recovery_safe(self) -> bool:
        try:
            from core.recovery_coordinator import RecoveryState
            state = self.runtime.recovery.assess().state
            return state in (RecoveryState.FRESH, RecoveryState.SAFE_TO_RESUME)
        except Exception:
            return False

    def _risk_approved(self) -> bool:
        # Risk approval is an explicit deployment control. It defaults to
        # blocked rather than assuming that a stale or missing risk policy is OK.
        return self._env_bool("CONTROLADOR_REAL_RISK_APPROVED")

    def _dependencies(self):
        authorization = self._authorization()
        broker_available = self._broker_available()
        safety = RealSafetyGate().evaluate(
            authorization_active=authorization.active,
            kill_switch_clear=self.runtime.kill_switch.allows_execution(),
            market_healthy=self._market_healthy(),
            recovery_safe=self._recovery_safe(),
            risk_approved=self._risk_approved(),
            broker_available=broker_available,
        )
        admission_id = os.environ.get("CONTROLADOR_REAL_ADMISSION_ID", "").strip()
        audit_verified = (
            self._env_bool("CONTROLADOR_REAL_AUDIT_VERIFIED")
            and bool(admission_id)
            and authorization.audit_id != "real-disabled"
        )
        admission = RealAdmissionBoundary().admit(
            admission_id=admission_id or "real-disabled",
            audit_id=authorization.audit_id,
            audit_verified=audit_verified,
            authorization_active=authorization.active,
            safety_ready=safety.ready,
            broker_available=broker_available,
            broker_id=self.broker_id,
        )
        return authorization, safety, admission

    def status(self) -> dict[str, Any]:
        authorization, safety, admission = self._dependencies()
        broker_available = self._broker_available()
        return {
            "provider": self.broker_id,
            "explicitly_enabled": authorization.explicitly_enabled,
            "real_execution_allowed": authorization.real_execution_allowed,
            "authorization_active": authorization.active,
            "audit_verified": self._env_bool("CONTROLADOR_REAL_AUDIT_VERIFIED"),
            "risk_approved": self._risk_approved(),
            "broker_available": broker_available,
            "market_healthy": self._market_healthy(),
            "recovery_safe": self._recovery_safe(),
            "safety_ready": safety.ready,
            "safety_reasons": safety.reasons,
            "admitted": admission.admitted,
            "admission_reasons": admission.reasons,
            "confirmation_ttl_seconds": int(self.confirmation._ttl.total_seconds()),
            "pending_confirmations": len(self.confirmation._pending),
            "real_dispatch": "MANUAL_CONFIRMATION_REQUIRED",
        }

    @staticmethod
    def _request(
        *,
        request_id: str,
        symbol: str,
        signal: str,
        amount: float,
        duration_seconds: int,
    ) -> ExecutionRequest:
        from core.models import Signal

        return ExecutionRequest(
            symbol=symbol.strip(),
            signal=Signal(str(signal).strip().upper()),
            amount=float(amount),
            duration_seconds=int(duration_seconds),
            mode=ExecutionMode.REAL,
            request_id=request_id.strip(),
        )

    def prepare(self, *, request_id: str, symbol: str, signal: str, amount: float, duration_seconds: int):
        authorization, safety, admission = self._dependencies()
        if not authorization.active:
            raise PermissionError("REAL não está explicitamente habilitado.")
        if not safety.ready:
            raise PermissionError("REAL bloqueado pela barreira de segurança: " + "; ".join(safety.reasons))
        if not admission.admitted:
            raise PermissionError("REAL não admitido: " + "; ".join(admission.reasons))
        request = self._request(
            request_id=request_id,
            symbol=symbol,
            signal=signal,
            amount=amount,
            duration_seconds=duration_seconds,
        )
        confirmation = self.confirmation.prepare(request=request)
        return {
            "confirmation_id": confirmation.confirmation_id,
            "request_id": confirmation.request_id,
            "request_fingerprint": confirmation.request_fingerprint,
            "created_at": confirmation.created_at.isoformat(),
            "expires_at": confirmation.expires_at.isoformat(),
            "broker": self.broker_id,
            "mode": "REAL",
            "human_action_required": True,
        }

    def confirm(
        self,
        *,
        confirmation_id: str,
        request_id: str,
        symbol: str,
        signal: str,
        amount: float,
        duration_seconds: int,
    ) -> RealGatewayResult:
        authorization, safety, admission = self._dependencies()
        request = self._request(
            request_id=request_id,
            symbol=symbol,
            signal=signal,
            amount=amount,
            duration_seconds=duration_seconds,
        )
        return self.confirmation.confirm(
            confirmation_id=confirmation_id,
            request=request,
            broker=self.broker_id,
            authorization=authorization,
            admission=admission,
            safety=safety,
            gateway=self.gateway,
        )

    def reconcile(self, *, request_id: str, executed: bool) -> None:
        self.gateway.reconcile_unknown(request_id, executed=bool(executed))
