"""User-defined context profiles for leverage calculations.

Profiles are context only: they are not identity proof, permission, or authorization.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

@dataclass(frozen=True)
class LeverageProfile:
    profile_id: str
    display_name: str
    account_currency: str
    capital_available: Decimal | None = None
    maximum_loss: Decimal | None = None
    active: bool = True
    def validate(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip() or not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("profile_id_and_display_name_required")
        if not isinstance(self.account_currency, str) or not self.account_currency.strip():
            raise ValueError("account_currency_required")
        for value, error in ((self.capital_available, "capital_available_must_be_non_negative"), (self.maximum_loss, "maximum_loss_must_be_non_negative")):
            if value is not None:
                decimal_value = Decimal(str(value))
                if not decimal_value.is_finite() or decimal_value < 0:
                    raise ValueError(error)

class LeverageProfileStore:
    def __init__(self) -> None:
        self._profiles: dict[str, LeverageProfile] = {}
    def put(self, profile: LeverageProfile) -> None:
        profile.validate(); self._profiles[profile.profile_id] = profile
    def get(self, profile_id: str) -> LeverageProfile | None:
        return self._profiles.get(profile_id)
    def list_active(self) -> tuple[LeverageProfile, ...]:
        return tuple(p for p in self._profiles.values() if p.active)
