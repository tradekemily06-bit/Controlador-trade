from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RealReleaseState(str, Enum):
    RELEASED = "RELEASED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RealReleaseClosure:
    release_id: str
    state: RealReleaseState
    baseline: str
    reasons: tuple[str, ...]

    @property
    def released(self) -> bool:
        return self.state is RealReleaseState.RELEASED


class RealReleaseClosureBoundary:
    def close(self, *, release_id: str, p116_verified: bool, p117_admitted: bool,
              p118_available: bool, multi_broker_boundary: bool) -> RealReleaseClosure:
        if not release_id.strip():
            raise ValueError("release_id é obrigatório.")
        reasons = []
        for ok, label in (
            (p116_verified, "P116 não verificado"),
            (p117_admitted, "P117 não admitido"),
            (p118_available, "P118 indisponível"),
            (multi_broker_boundary, "arquitetura multi-corretora não verificada"),
        ):
            if not ok:
                reasons.append(label)
        state = RealReleaseState.RELEASED if not reasons else RealReleaseState.BLOCKED
        return RealReleaseClosure(release_id, state, "P111-P119", tuple(reasons))
