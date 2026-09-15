from __future__ import annotations

"""Durable authoritative DEMO risk-state storage.

This store is deliberately separate from decision payloads. A browser/request
cannot establish account state merely by supplying an ``OperationalState``.
Only an internal trusted adapter/reconciliation boundary should call
``replace``. Missing, stale or corrupt state is represented as unavailable and
must fail closed at the execution boundary.
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .file_lock import exclusive_file_lock
from .operational_state import OperationalState
from .risk_state_fingerprint import risk_state_fingerprint


class DemoRiskStateUnavailable(RuntimeError):
    """Raised when the authoritative DEMO risk state cannot be trusted."""


class DemoRiskStateStore:
    """Cross-process, atomic store for the authoritative DEMO risk snapshot."""

    VERSION = 1
    TRUSTED_SOURCES = frozenset({"demo-account-adapter", "reconciliation"})

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)

    def _lock(self):
        return exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock"))

    def dispatch_lock(self) -> Iterator[None]:
        """Serialize DEMO state publication against the final dispatch window.

        The execution gateway may hold this lock across its final risk identity
        check and the local DEMO executor call. A trusted adapter therefore
        cannot publish a new account/exposure state in the middle of that
        critical section. This closes the local read/check/dispatch race while
        preserving fail-closed behavior when the lock is unavailable.
        """
        return self._lock()

    @staticmethod
    def _encode_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @classmethod
    def _encode_state(cls, state: OperationalState) -> dict[str, object]:
        values = asdict(state)
        values["last_processed_candle"] = cls._encode_datetime(state.last_processed_candle)
        return values

    @staticmethod
    def _decode_state(raw: object) -> OperationalState:
        if not isinstance(raw, dict):
            raise DemoRiskStateUnavailable("estado de risco DEMO ausente ou inválido")
        values = dict(raw)
        timestamp = values.get("last_processed_candle")
        if timestamp is not None:
            if not isinstance(timestamp, str):
                raise DemoRiskStateUnavailable("timestamp do estado de risco DEMO inválido")
            try:
                values["last_processed_candle"] = datetime.fromisoformat(timestamp)
            except ValueError as exc:
                raise DemoRiskStateUnavailable("timestamp do estado de risco DEMO inválido") from exc
        try:
            return OperationalState(**values)
        except (TypeError, ValueError) as exc:
            raise DemoRiskStateUnavailable("estado de risco DEMO inválido") from exc

    def _read_locked(self) -> dict[str, object]:
        if not self.path.exists():
            raise DemoRiskStateUnavailable("estado de risco DEMO ainda não foi sincronizado")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DemoRiskStateUnavailable("estado de risco DEMO indisponível") from exc
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            raise DemoRiskStateUnavailable("versão do estado de risco DEMO não suportada")
        return payload

    @classmethod
    def _validate_payload(cls, payload: dict[str, object]) -> tuple[OperationalState, str, str]:
        source = payload.get("source")
        stored_fingerprint = payload.get("fingerprint")
        updated_at = payload.get("updated_at")
        if source not in cls.TRUSTED_SOURCES:
            raise DemoRiskStateUnavailable("origem do estado de risco DEMO não é confiável")
        if not isinstance(stored_fingerprint, str) or len(stored_fingerprint) != 64:
            raise DemoRiskStateUnavailable("fingerprint do estado de risco DEMO inválido")
        if not isinstance(updated_at, str) or not updated_at.strip():
            raise DemoRiskStateUnavailable("timestamp do estado de risco DEMO ausente")
        try:
            datetime.fromisoformat(updated_at)
        except ValueError as exc:
            raise DemoRiskStateUnavailable("timestamp do estado de risco DEMO inválido") from exc
        state = cls._decode_state(payload.get("state"))
        if risk_state_fingerprint(state) != stored_fingerprint:
            raise DemoRiskStateUnavailable("fingerprint do estado de risco DEMO não confere")
        if not state.risk_fields_available():
            raise DemoRiskStateUnavailable("campos obrigatórios de risco DEMO indisponíveis")
        return state, stored_fingerprint, source

    def replace(self, state: OperationalState, *, source: str) -> str:
        """Atomically publish a trusted state and return its fingerprint.

        This method is intentionally not used by HTTP/API boundaries. The
        caller must be an internal adapter or reconciliation component whose
        source is explicitly allow-listed above.
        """
        if not isinstance(state, OperationalState):
            raise ValueError("estado operacional inválido")
        if source not in self.TRUSTED_SOURCES:
            raise PermissionError("origem não autorizada para publicar estado de risco DEMO")
        if not state.risk_fields_available():
            raise DemoRiskStateUnavailable("campos obrigatórios de risco DEMO indisponíveis")
        fingerprint = risk_state_fingerprint(state)
        payload = {
            "version": self.VERSION,
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint": fingerprint,
            "state": self._encode_state(state),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        with self._lock():
            try:
                temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
                with temporary.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:
                    pass
        return fingerprint

    def current(self) -> OperationalState:
        """Return the validated authoritative state or fail closed."""
        with self._lock():
            state, _, _ = self._validate_payload(self._read_locked())
            return state

    def fingerprint(self) -> str:
        """Return the validated identity used by execution race checks."""
        with self._lock():
            _, fingerprint, _ = self._validate_payload(self._read_locked())
            return fingerprint

    def status(self) -> dict[str, object]:
        """Expose non-sensitive health metadata without exposing account values."""
        with self._lock():
            try:
                payload = self._read_locked()
                _, fingerprint, source = self._validate_payload(payload)
            except DemoRiskStateUnavailable as exc:
                return {"available": False, "reason": str(exc)}
            return {
                "available": True,
                "source": source,
                "fingerprint": fingerprint,
                "updated_at": payload["updated_at"],
            }
