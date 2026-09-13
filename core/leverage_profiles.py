"""Minimal person profiles used to contextualize leverage requests.

Names are intentionally user-defined. A profile is an identifier/context boundary,
not permission, identity proof, or authorization. No credentials or secrets belong here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class LeverageProfile:
    profile_id: str
    display_name: str
    account_currency: str
    capital_available: Decimal | None = None
    maximum_loss: Decimal | None = None
    active: bool = True

    def validate(self) -> None:
        if not self.profile_id.strip() or not self.display_name.strip():
            raise ValueError("profile_id_and_display_name_required")
        if not self.account_currency.strip():
            raise ValueError("account_currency_required")
        if self.capital_available is not None and self.capital_available < 0:
            raise ValueError("capital_available_must_be_non_negative")
        if self.maximum_loss is not None and self.maximum_loss < 0:
            raise ValueError("maximum_loss_must_be_non_negative")


class LeverageProfileStore:
    """In-memory reference store; persistence can be added behind the same boundary."""

    def __init__(self) -> None:
        self._profiles: dict[str, LeverageProfile] = {}

    def put(self, profile: LeverageProfile) -> None:
        profile.validate()
        self._profiles[profile.profile_id] = profile

    def get(self, profile_id: str) -> LeverageProfile | None:
        return self._profiles.get(profile_id)

    def list_active(self) -> tuple[LeverageProfile, ...]:
        return tuple(p for p in self._profiles.values() if p.active)
