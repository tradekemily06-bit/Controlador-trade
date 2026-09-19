from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

from core.durable_json import atomic_write_json, locked_path, read_json


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


class ExecutionLedger:
    _request_lock_local = threading.local()
    _real_lock_local = threading.local()

    """Persistent request state for restart-safe REAL execution idempotency."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._states: dict[str, ExecutionLedgerStatus] = {}
        self._external_ids: dict[str, str] = {}
        self._load()

    def _load_unlocked(self) -> None:
        self._states = {}
        self._external_ids = {}
        try:
            payload = read_json(self.path, {})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._external_ids = self._decode(payload)

    def _load(self) -> None:
        try:
            with locked_path(self.path):
                self._load_unlocked()
        except ValueError:
            raise
        except OSError as exc:
            raise ValueError("ledger de execução inválido.") from exc

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, str]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return {item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {}
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        states: dict[str, ExecutionLedgerStatus] = {}
        external_ids: dict[str, str] = {}
        for request_id, raw_status in payload.items():
            if not isinstance(request_id, str) or not request_id.strip() or request_id != request_id.strip():
                raise ValueError("ledger de execução inválido.")
            external_id = None
            if isinstance(raw_status, dict):