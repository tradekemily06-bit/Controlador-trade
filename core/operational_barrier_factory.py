"""Build the single fail-closed operational barrier from runtime state."""
from __future__ import annotations

from core.global_operational_barrier import GlobalOperationalBarrier, RemediationMode, SafetyComponent
from core.operational_runtime import OperationalRuntime


def build_global_operational_barrier(runtime: OperationalRuntime | None) -> GlobalOperationalBarrier:
    """Create a fresh barrier from authoritative runtime state.

    The barrier is intentionally rebuilt for every decision/check so no stale
    health snapshot can accidentally authorize an operation. Diagnostics can
    still run while the barrier is blocked; only operationally meaningful
    decisions are denied.

    The persisted safety store is also authoritative for the kill switch. This
    matters for multi-worker deployments: a worker that did not receive the
    in-memory state change must still be blocked immediately after another
    worker activates the persisted kill switch.
    """
    if runtime is None:
        return GlobalOperationalBarrier((
            SafetyComponent(
                "operational-runtime",
                False,
                "runtime operacional não conectado",
                RemediationMode.MANUAL_REQUIRED,
            ),
        ))

    components: list[SafetyComponent] = []

    try:
        incident = runtime.incident_manager.status()
        components.append(SafetyComponent(
            "technical-incident",
            incident.get("execution_blocked") is False,
            str(incident.get("reason") or "incidente técnico ativo"),
            RemediationMode.MANUAL_REQUIRED,
        ))
    except Exception as exc:
        components.append(SafetyComponent("technical-incident", False, f"estado de incidente indisponível: {type(exc).__name__}"))

    try:
        local_kill = runtime.kill_switch.state
        _audit, persisted_kill = runtime.safety_store.load()
        persisted_enabled = persisted_kill.state.enabled
        local_enabled = local_kill.enabled
        components.append(SafetyComponent(
            "kill-switch",
            local_enabled is False and persisted_enabled is False,
            (
                persisted_kill.state.reason
                or local_kill.reason
                or "kill switch ativo"
            ),
            RemediationMode.NEVER_AUTO,
        ))
        components.append(SafetyComponent(
            "operational-safety-store",
            True,
            "estado de segurança persistido legível e consistente",
            RemediationMode.NEVER_AUTO,
        ))
    except Exception as exc:
        components.append(SafetyComponent(
            "kill-switch",
            False,
            f"estado autoritativo do kill switch indisponível: {type(exc).__name__}",
            RemediationMode.NEVER_AUTO,
        ))
        components.append(SafetyComponent(
            "operational-safety-store",
            False,
            f"estado de segurança indisponível: {type(exc).__name__}",
            RemediationMode.NEVER_AUTO,
        ))

    try:
        maintenance = runtime.maintenance.status()
        components.append(SafetyComponent(
            "maintenance",
            maintenance.get("execution_blocked") is False,
            f"manutenção: {maintenance.get('status', 'UNKNOWN')}",
            RemediationMode.MANUAL_REQUIRED,
        ))
    except Exception as exc:
        components.append(SafetyComponent("maintenance", False, f"estado de manutenção indisponível: {type(exc).__name__}"))

    try:
        market = runtime.market_data.status()
        components.append(SafetyComponent(
            "market-data-integrity",
            market.get("safe_for_analysis") is True,
            str(market.get("message") or "dados de mercado não estão seguros para análise"),
            RemediationMode.MANUAL_REQUIRED,
        ))
    except Exception as exc:
        components.append(SafetyComponent("market-data-integrity", False, f"integridade de mercado indisponível: {type(exc).__name__}", RemediationMode.MANUAL_REQUIRED))

    try:
        recovery = runtime.recovery.assess()
        components.append(SafetyComponent(
            "execution-recovery",
            recovery.can_resume is True,
            recovery.message,
            RemediationMode.MANUAL_REQUIRED,
        ))
    except Exception as exc:
        components.append(SafetyComponent("execution-recovery", False, f"estado de recuperação indisponível: {type(exc).__name__}"))

    try:
        health = runtime.health.assess()
        components.append(SafetyComponent(
            "runtime-health",
            health.state.value == "HEALTHY",
            health.message,
            RemediationMode.MANUAL_REQUIRED,
        ))
    except Exception as exc:
        components.append(SafetyComponent("runtime-health", False, f"saúde do runtime indisponível: {type(exc).__name__}"))

    return GlobalOperationalBarrier(components)
