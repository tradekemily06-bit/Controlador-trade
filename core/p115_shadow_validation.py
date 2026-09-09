from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShadowValidationResult:
    validation_id: str
    passed: bool
    checks: tuple[str, ...]
    failures: tuple[str, ...]


class ShadowValidationBoundary:
    """Deterministic pre-REAL validation; never calls a live broker."""

    def validate(self, *, validation_id: str, adapter_available: bool,
                 real_safety_ready: bool, duplicate_blocked: bool,
                 kill_switch_blocked: bool, real_mode_rejected_by_shadow: bool) -> ShadowValidationResult:
        if not validation_id.strip():
            raise ValueError("validation_id é obrigatório.")
        checks = (
            "adapter availability",
            "REAL safety readiness",
            "duplicate protection",
            "kill switch protection",
            "shadow isolation",
        )
        failures = []
        for ok, label in (
            (adapter_available, "adapter indisponível"),
            (real_safety_ready, "segurança REAL não pronta"),
            (duplicate_blocked, "duplicidade não bloqueada"),
            (kill_switch_blocked, "kill switch não bloqueou"),
            (real_mode_rejected_by_shadow, "shadow não está isolado"),
        ):
            if not ok:
                failures.append(label)
        return ShadowValidationResult(validation_id, not failures, checks, tuple(failures))
