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
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState
from execution.ports import (
    ExecutionMode, ExecutionRequest, PositionCloseObservation,
    PositionCloseObservationStatus,
)
from execution.position_close_store import PositionCloseState, PositionCloseStore
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
        self.root.mkdir(parents=True, exist_ok=True)
        self.position_closes = PositionCloseStore(self.root / "real-position-closes.json")
        self.symbol = symbol
        self.broker_id = os.environ.get("CONTROLADOR_REAL_BROKER_ID", IC_MARKETS_MT5_REAL).strip().lower() or IC_MARKETS_MT5_REAL
        self.registry: BrokerRegistry = build_real_registry(symbol=symbol)
        if self.broker_id not in self.registry.names():
            # Fail closed: a configured broker is not considered supported merely
            # because an arbitrary identifier was supplied.
            self.broker_id = "__unsupported__"
        self.gateway = RealExecutionGateway(
            BrokerAdapterGateway(self.registry),
            self.runtime.execution_ledger,
            self.runtime.execution_lifecycle,
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

    def _position_close_recovery_required(self) -> bool:
        try:
            return any(
                record.state in (PositionCloseState.REQUESTED, PositionCloseState.UNKNOWN)
                for record in self.position_closes.records()
            )
        except Exception:
            # Missing/corrupt close history must fail closed for new REAL entries.
            return True

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
        try:
            close_records = self.position_closes.records()
            unresolved_close_count = sum(
                record.state in (PositionCloseState.REQUESTED, PositionCloseState.UNKNOWN)
                for record in close_records
            )
        except Exception:
            unresolved_close_count = None
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
            "position_close_recovery_required": self._position_close_recovery_required(),
            "unresolved_position_closes": unresolved_close_count,
            "position_close_recovery_items": (
                [
                    {
                        "request_id": record.request_id,
                        "external_id": record.external_id,
                        "state": record.state.value,
                        "attempt": record.attempt,
                        "updated_at": record.updated_at.isoformat(),
                        "message": record.message,
                    }
                    for record in close_records
                    if record.state in (PositionCloseState.REQUESTED, PositionCloseState.UNKNOWN)
                ]
                if unresolved_close_count is not None
                else []
            ),
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
        if self._position_close_recovery_required():
            raise PermissionError("REAL bloqueado: existe fechamento de posição sem reconciliação.")
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
        """Serialize REAL final authorization and dispatch with Kill Switch activation."""
        with self.runtime.kill_switch.execution_lock():
            return self._confirm_locked(
                confirmation_id=confirmation_id,
                request_id=request_id,
                symbol=symbol,
                signal=signal,
                amount=amount,
                duration_seconds=duration_seconds,
            )

    def _confirm_locked(
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
        if self._position_close_recovery_required():
            raise PermissionError("REAL bloqueado: existe fechamento de posição sem reconciliação.")
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

    def close_and_reconcile(self, *, request_id: str, external_id: str):
        # Serialize with REAL dispatch and Kill Switch activation. Closing is
        # risk-reducing, so do not call guard() here.
        with self.runtime.kill_switch.execution_lock():
            return self._close_and_reconcile_locked(
                request_id=request_id,
                external_id=external_id,
            )

    @staticmethod
    def _valid_account_fingerprint(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 32
            and all(char in "0123456789abcdef" for char in value)
        )

    def _close_and_reconcile_locked(self, *, request_id: str, external_id: str):
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id REAL inválido.")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id REAL inválido.")
        record = self.runtime.execution_ledger.record_for(request_id)
        if record is None:
            raise ValueError("request_id REAL não encontrado no ledger.")
        if record.status is not ExecutionLedgerStatus.ACCEPTED:
            raise ValueError("somente uma execução REAL ACCEPTED pode ser fechada.")
        if record.external_id != external_id.strip():
            raise ValueError("external_id não corresponde à identidade persistida do request REAL.")
        if not self._valid_account_fingerprint(record.account_fingerprint):
            raise ValueError(
                "fechamento REAL bloqueado: ledger não possui impressão digital confiável da conta de abertura."
            )

        # Persist the intent before touching the broker. A crash or ambiguous
        # adapter result remains blocked from automatic retry until reconciled.
        self.position_closes.begin(request_id, external_id.strip())
        try:
            adapter = self.registry.get(self.broker_id)
            close = adapter.close_position(
                external_id.strip(),
                expected_account_fingerprint=record.account_fingerprint,
            )
        except Exception as exc:
            self.position_closes.finish(
                request_id,
                PositionCloseState.UNKNOWN,
                message=f"resultado do fechamento incerto após erro do adaptador: {type(exc).__name__}",
            )
            raise

        state = PositionCloseState.CLOSED if close.accepted else PositionCloseState.UNKNOWN
        self.position_closes.finish(
            request_id,
            state,
            message=close.message,
            close_external_id=close.external_id if close.accepted else None,
        )
        # The opening execution ledger/lifecycle remain unchanged: closing a
        # position is a separate lifecycle and must not rewrite order opening.
        return close

    def reconcile_position_close(self, *, request_id: str, external_id: str) -> dict[str, Any]:
        """Read broker evidence and resolve a pending/unknown close without sending an order."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id de fechamento inválido.")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id de fechamento inválido.")
        with self.runtime.kill_switch.execution_lock():
            record = self.position_closes.get(request_id)
            if record is None:
                raise ValueError("solicitação de fechamento não encontrada.")
            if record.external_id != external_id.strip():
                raise ValueError("external_id não corresponde ao fechamento persistido.")
            opening_record = self.runtime.execution_ledger.record_for(request_id)
            if (
                opening_record is None
                or opening_record.status is not ExecutionLedgerStatus.ACCEPTED
                or opening_record.external_id != external_id.strip()
            ):
                raise ValueError("identidade de abertura não confere com o ledger persistido.")
            if not self._valid_account_fingerprint(opening_record.account_fingerprint):
                raise ValueError("reconciliação bloqueada: impressão digital da conta de abertura ausente ou inválida.")
            if record.state not in (PositionCloseState.REQUESTED, PositionCloseState.UNKNOWN):
                raise ValueError("somente fechamento REQUESTED ou UNKNOWN pode ser reconciliado.")
            adapter = self.registry.get(self.broker_id)
            observe = getattr(adapter, "reconcile_position_close", None)
            if not callable(observe):
                raise RuntimeError("adaptador não oferece reconciliação somente leitura de fechamento.")
            observation = observe(
                external_id.strip(),
                expected_account_fingerprint=opening_record.account_fingerprint,
            )
            if (
                not isinstance(observation, PositionCloseObservation)
                or not isinstance(observation.status, PositionCloseObservationStatus)
                or not isinstance(observation.message, str)
            ):
                raise RuntimeError("adaptador retornou observação de fechamento inválida.")
            mapping = {
                PositionCloseObservationStatus.CLOSED: PositionCloseState.CLOSED,
                PositionCloseObservationStatus.OPEN: PositionCloseState.OPEN,
                PositionCloseObservationStatus.UNKNOWN: PositionCloseState.UNKNOWN,
            }
            resolved = self.position_closes.reconcile(
                request_id,
                mapping[observation.status],
                message=observation.message,
            )
            return {
                "request_id": resolved.request_id,
                "state": resolved.state.value,
                "message": resolved.message,
                "read_only": True,
                "order_sent": False,
            }

    def reconcile(self, *, request_id: str, executed: bool) -> None:
        if not isinstance(executed, bool):
            raise ValueError("executed deve ser booleano verdadeiro ou falso.")
        self.gateway.reconcile_unknown(request_id, executed=executed)
