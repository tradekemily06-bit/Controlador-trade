from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


_RELEASE_ISSUER = object()


class RealReleaseState(str, Enum):
    RELEASED = "RELEASED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RealReleaseClosure:
    release_id: str
    state: RealReleaseState
    baseline: str
    reasons: tuple[str, ...]
    _issuer: object = field(default=None, repr=False, compare=False)

    @property
    def released(self) -> bool:
        return self.state is RealReleaseState.RELEASED and self._issuer is _RELEASE_ISSUER

    @property
    def issued_by_boundary(self) -> bool:
        return self._issuer is _RELEASE_ISSUER


class RealReleaseClosureBoundary:
    def __init__(self, *, capability: object | None = None) -> None:
        if capability is not _RELEASE_ISSUER:
            raise ValueError("emissor de release REAL não pode ser criado por código externo.")
        self._capability = capability

    @classmethod
    def _internal(cls) -> "RealReleaseClosureBoundary":
        return cls(capability=_RELEASE_ISSUER)

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
        return RealReleaseClosure(release_id, state, "P111-P119", tuple(reasons), _RELEASE_ISSUER)
