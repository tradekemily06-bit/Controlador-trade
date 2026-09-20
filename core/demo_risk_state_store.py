from __future__ import annotations

"""Durable authoritative DEMO risk-state storage."""
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
    pass


class DemoRiskStateStore:
    VERSION = 1
    MAX_FILE_BYTES = 4 * 1024 * 1024
    TRUSTED_SOURCES = frozenset({"demo-account-adapter", "reconciliation"})
    DEFAULT_MAX_AGE_SECONDS = 30.0
    MAX_FUTURE_SKEW_SECONDS = 2.0

    def __init__(self, path: str | Path, *, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        if not isinstance(max_age_seconds, (int, float)) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds deve ser maior que zero.")
        self.path = Path(path)
        self.max_age_seconds = float(max_age_seconds)

    def _lock(self):
        return exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock"))

    def dispatch_lock(self) -> Iterator[None]:
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
            stat = self.path.lstat()
            if self.path.is_symlink() or not self.path.is_file():
                raise DemoRiskStateUnavailable("estado de risco DEMO deve ser um arquivo regular")
            if stat.st_size > self.MAX_FILE_BYTES:
                raise DemoRiskStateUnavailable("estado de risco DEMO excede o limite permitido")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except DemoRiskStateUnavailable:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DemoRiskStateUnavailable("estado de risco DEMO indisponível") from exc
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            raise DemoRiskStateUnavailable("versão do estado de risco DEMO não suportada")
        return payload

    def _validate_payload(
        self, payload: dict[str, object], *, now: datetime | None = None
    ) -> tuple[OperationalState, str, str]:
        source, stored_fingerprint, updated_at = (
            payload.get("source"),
            payload.get("fingerprint"),
            payload.get("updated_at"),
        )
        if source not in self.TRUSTED_SOURCES:
            raise DemoRiskStateUnavailable("origem do estado de risco DEMO não é confiável")
        if not isinstance(stored_fingerprint, str) or len(stored_fingerprint) != 64:
            raise DemoRiskStateUnavailable("fingerprint do estado de risco DEMO inválido")
        if not isinstance(updated_at, str) or not updated_at.strip():
            raise DemoRiskStateUnavailable("timestamp do estado de risco DEMO ausente")
        try:
            updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DemoRiskStateUnavailable("timestamp do estado de risco DEMO inválido") from exc
        if updated_dt.tzinfo is None:
            raise DemoRiskStateUnavailable("timestamp do estado de risco DEMO deve conter timezone")
        reference = now or datetime.now(timezone.utc)
        age = (reference - updated_dt).total_seconds()
        if age < -self.MAX_FUTURE_SKEW_SECONDS:
            raise DemoRiskStateUnavailable("estado de risco DEMO possui timestamp futuro inválido")
        if age > self.max_age_seconds:
            raise DemoRiskStateUnavailable("estado de risco DEMO está desatualizado")
        state = self._decode_state(payload.get("state"))
        if risk_state_fingerprint(state) != stored_fingerprint:
            raise DemoRiskStateUnavailable("fingerprint do estado de risco DEMO não confere")
        if not state.risk_fields_available():
            raise DemoRiskStateUnavailable("campos obrigatórios de risco DEMO indisponíveis")
        return state, stored_fingerprint, source

    def replace(self, state: OperationalState, *, source: str) -> str:
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
        if self.path.parent.resolve(strict=True) != self.path.parent.absolute():
            raise OSError("diretório do estado de risco DEMO não pode ser symlink")
        if self.path.exists():
            stat = self.path.lstat()
            if self.path.is_symlink() or not self.path.is_file():
                raise OSError("estado de risco DEMO deve ser um arquivo regular")
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        with self._lock():
            try:
                encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                if len(encoded) > self.MAX_FILE_BYTES:
                    raise ValueError("estado de risco DEMO excede o limite permitido")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                fd = None
                try:
                    fd = os.open(temporary, flags, 0o600)
                    with os.fdopen(fd, "wb") as handle:
                        fd = None
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())
                except FileExistsError as exc:
                    raise RuntimeError("arquivo temporário do estado de risco DEMO já existe") from exc
                finally:
                    if fd is not None:
                        os.close(fd)
                with temporary.open("rb") as handle:
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                try:
                    directory_fd = os.open(self.path.parent, os.O_RDONLY)
                except OSError:
                    directory_fd = None
                if directory_fd is not None:
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            finally:
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:
                    pass
        return fingerprint

    def current_risk_state(self) -> OperationalState:
        """Return the current authoritative risk state for the execution gateway."""
        return self.current()

    def current(self) -> OperationalState:
        with self._lock():
            return self._validate_payload(self._read_locked())[0]

    def fingerprint(self) -> str:
        with self._lock():
            return self._validate_payload(self._read_locked())[1]

    def status(self) -> dict[str, object]:
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
