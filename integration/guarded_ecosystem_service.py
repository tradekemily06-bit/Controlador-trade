"""Production-facing service guard for the global fail-closed barrier."""
from __future__ import annotations

from typing import Any, Iterable

from core.models import AnalysisResult, Signal
from core.operational_barrier_factory import build_global_operational_barrier
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.p137_operational_risk_bridge import OperationalRiskBridge


class GuardedEcosystemService(ConfiguredEcosystemService):
    """Configured service that cannot emit an operational BUY/SELL while blocked."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Bind the risk boundary to the same runtime barrier AND authoritative
        # runtime risk-state source. The provider is evaluated fresh on every
        # risk decision, so a kill switch, incident, maintenance state,
        # stale-market state, runtime failure, or spoofed payload cannot be
        # hidden behind a startup snapshot.
        if self.operational_runtime is not None:
            self.operational_risk_bridge = OperationalRiskBridge(
                self.risk,
                incident_manager=self.operational_runtime.incident_manager,
                operational_barrier_provider=lambda: build_global_operational_barrier(self.operational_runtime),
                operational_state_provider=self.operational_runtime.risk_state_provider,
            )

    def operational_barrier(self):
        return build_global_operational_barrier(self.operational_runtime)

    def operational_barrier_status(self) -> dict[str, object]:
        decision = self.operational_barrier().evaluate()
        return {
            "status": decision.status.value,
            "operationally_allowed": decision.operationally_allowed,
            "reason": decision.reason,
            "blocking_components": list(decision.blocking_components),
            "repaired_components": list(decision.repaired_components),
        }

    def remediate_operational_barrier(self) -> dict[str, object]:
        """Attempt only repairs explicitly classified as AUTO_SAFE.

        A successful repair never grants authorization. The barrier is rebuilt
        and evaluated again before anything operational can proceed.
        """
        before = self.operational_barrier().evaluate()
        repairs = self.operational_barrier().remediate()
        after = self.operational_barrier().evaluate()
        return {
            "before": {
                "status": before.status.value,
                "reason": before.reason,
                "blocking_components": list(before.blocking_components),
            },
            "repairs": [
                {
                    "component": item.component,
                    "mode": item.mode.value,
                    "attempted": item.attempted,
                    "succeeded": item.succeeded,
                    "detail": item.detail,
                }
                for item in repairs
            ],
            "after": {
                "status": after.status.value,
                "operationally_allowed": after.operationally_allowed,
                "reason": after.reason,
                "blocking_components": list(after.blocking_components),
            },
            "authorization_rule": "repair_success_never_authorizes; full revalidation required",
        }

    def system_status(self) -> dict[str, Any]:
        result = dict(super().system_status())
        result["global_operational_barrier"] = self.operational_barrier_status()
        return result

    def public_status(self) -> dict[str, Any]:
        result = dict(super().public_status())
        result["global_operational_barrier"] = self.operational_barrier_status()
        return result

    def analyze(self, payload: dict[str, Any], *, persist: bool = True, subject_id: str | None = None, tenant_id: str | None = None):
        decision = self.operational_barrier().evaluate()
        if not decision.operationally_allowed:
            owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
            result = AnalysisResult(
                signal=Signal.AGUARDAR,
                score=float(payload.get("score", 0)),
                reason=f"Análise operacional bloqueada: {decision.reason}.",
                confirmed=False,
                symbol=payload.get("symbol"),
                timeframe=payload.get("timeframe"),
            )
            return self._record_analysis(result, persist=persist, owner=owner)
        return super().analyze(payload, persist=persist, subject_id=subject_id, tenant_id=tenant_id)

    def replay(self, cases: Iterable[dict[str, Any]], *, subject_id: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """Replay is research/simulation and never authorizes live operations."""
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        from core.replay_policy import prevalidate_replay_cases
        accepted_cases = prevalidate_replay_cases(cases)
        records = []
        for payload in accepted_cases:
            records.append(super().analyze(payload, persist=False, subject_id=owner.subject_id if owner else None, tenant_id=owner.tenant_id if owner else None))
        self._persist_records(records)
        return [{"step": index, **record.to_dict()} for index, record in enumerate(records, start=1)]

    def risk_status(self) -> dict[str, Any]:
        decision = self.operational_barrier().evaluate()
        if not decision.operationally_allowed:
            return {
                "allowed": False,
                "reason": f"operação bloqueada pela barreira global: {decision.reason}",
                "configured_limits": {
                    "daily_loss_limit": self.risk.daily_loss_limit,
                    "max_operations": self.risk.max_operations,
                    "max_consecutive_losses": self.risk.max_consecutive_losses,
                },
                "news_provider": "UNCONFIGURED",
                "global_barrier": self.operational_barrier_status(),
            }
        result = super().risk_status()
        result["global_barrier"] = self.operational_barrier_status()
        return result
