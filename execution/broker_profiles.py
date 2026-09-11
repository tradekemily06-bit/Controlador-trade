from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerProfile:
    """Non-secret broker metadata used to select an execution environment."""

    name: str
    platform: str
    server: str
    demo_only: bool = True

    def __post_init__(self) -> None:
        for field_name in ("name", "platform", "server"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} deve ser texto não vazio.")
        if not isinstance(self.demo_only, bool):
            raise ValueError("demo_only deve ser booleano.")


IC_MARKETS_MT5_DEMO = BrokerProfile(
    name="IC Markets",
    platform="MT5",
    server="ICMarketsSC-Demo",
    demo_only=True,
)

LHFX_MT5_DEMO = BrokerProfile(
    name="LHFX",
    platform="MT5",
    server="LHFXSA-Negociação",
    demo_only=True,
)


def supported_demo_profiles() -> tuple[BrokerProfile, ...]:
    """Return configured demo environments without exposing account credentials."""
    return (IC_MARKETS_MT5_DEMO, LHFX_MT5_DEMO)
