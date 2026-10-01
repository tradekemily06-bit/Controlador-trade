from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.real_manual_confirmation_contract import RealManualConfirmation
from core.p114_real_safety_gate import RealSafetyReport
from core.p117_real_admission import RealAdmission
from execution.ports import ExecutionRequest
from execution.real_gateway import RealExecutionGateway, RealGatewayResult


class RealManualConfirmationGate:
    """Separates preparing a REAL order from the explicit human send action.

    Preparing creates no execution authority and never calls a broker. A
    confirmation is single-use, short-lived, and bound to the exact request.
    Pending confirmations are intentionally in-memory so a process restart
    cannot silently restore an armed REAL order.
    """

    def __init__(self, *, ttl_seconds: int = 60) -> None:
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 300:
            raise ValueError("ttl_seconds deve estar entre 1 e 300 segundos.")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._pending: dict[str, ManualRealConfirmation] = {}
        self._consumed: set[str] = set()

    @staticmethod
    def fingerprint(request: ExecutionRequest) -> str:
        if not isinstance(request, ExecutionRequest):
            raise ValueError("request inválido.")
        canonical = "|".join(
            (
                request.symbol.strip(),
                request.signal.value,
                f"{float(request.amount):.12g}",
                str(request.duration_seconds),
                request.mode.value,
                str(request.request_id or "").strip(),
            )
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def prepare(self, *, request: ExecutionRequest, now: datetime | None = None) -> RealManualConfirmation:
        if request.mode.value != "REAL":
            raise ValueError("confirmação manual REAL exige request REAL.")
        if not request.request_id or not request.request_id.strip():
            raise ValueError("request REAL exige request_id.")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now deve conter timezone.")
        confirmation = RealManualConfirmation(
            confirmation_id=secrets.token_urlsafe(24),
            request_id=request.request_id.strip(),
            request_fingerprint=self.fingerprint(request),
            created_at=current,
            expires_at=current + self._ttl,
        )
        self._pending[confirmation.confirmation_id] = confirmation
        return confirmation

    def confirm(
        self,
        *,
        confirmation_id: str,
        request: ExecutionRequest,
        broker: str,
        authorization: RealExecutionAuthorization,
        admission: RealAdmission,
        safety: RealSafetyReport,
        gateway: RealExecutionGateway,
        now: datetime | None = None,
    ) -> RealGatewayResult:
        if not isinstance(confirmation_id, str) or not confirmation_id.strip():
            raise ValueError("confirmation_id é obrigatório.")
        if confirmation_id in self._consumed:
            raise ValueError("confirmação REAL já consumida.")
        confirmation = self._pending.get(confirmation_id)
        if confirmation is None:
            raise ValueError("confirmação REAL inexistente, expirada ou invalidada.")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now deve conter timezone.")
        if current > confirmation.expires_at:
            self._pending.pop(confirmation_id, None)
            raise ValueError("confirmação REAL expirada.")
        if request.request_id != confirmation.request_id or self.fingerprint(request) != confirmation.request_fingerprint:
            raise ValueError("request REAL não corresponde à confirmação humana.")
        self._pending.pop(confirmation_id, None)
        self._consumed.add(confirmation_id)
        return gateway.execute(
            broker=broker,
            request_id=request.request_id,
            request=request,
            authorization=authorization,
            admission=admission,
            safety=safety,
        )
