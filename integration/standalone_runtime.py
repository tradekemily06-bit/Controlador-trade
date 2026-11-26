"""Persistent, broker-independent startup for the standalone analyst application."""
from __future__ import annotations

import os
from pathlib import Path

from analysis.decision_store import DecisionStore
from assistant.chat_service import EcosystemAssistant
from assistant.conversation_store import AssistantConversationStore
from core.runtime_process_lock import RuntimeProcessLock
from finance.fiscal_domestic_pending import FiscalDomesticPendingQueue
from finance.fiscal_identity import configured_fiscal_owner_id
from finance.fiscal_pending_queue import FiscalPendingQueue
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema
from integration.ecosystem_service import EcosystemService
from integration.standalone_application_factory import build_standalone_application


class StandaloneRuntime:
    """Owns one durable single-user runtime and its process-exclusive lock.

    This runtime intentionally does not instantiate MT5, a broker executor or
    the legacy operational runtime. Market-data adapters must be injected and
    validated separately before the Analysis area can produce a market reading.
    """

    def __init__(self, runtime_dir: str | Path | None = None) -> None:
        configured_identity = os.getenv("CONTROLADOR_SINGLE_USER_IDENTITY", "").strip()
        if not configured_identity:
            raise RuntimeError("CONTROLADOR_SINGLE_USER_IDENTITY precisa estar configurada")

        self.runtime_dir = Path(
            runtime_dir or os.getenv("CONTROLADOR_RUNTIME_DIR", ".runtime-standalone")
        ).resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.process_lock = RuntimeProcessLock(self.runtime_dir / "standalone-app.lock")
        self.process_lock.acquire()
        self.closed = False

        try:
            fiscal_database = self.runtime_dir / "fiscal-reserve.sqlite3"

            # The process lock must be held before migrations or repositories
            # touch the shared SQLite runtime.
            self.fiscal_owner_id = migrate_fiscal_schema(str(fiscal_database))
            self.fiscal_reserve = FiscalReserve(str(fiscal_database))
            self.foreign_pending = FiscalPendingQueue(str(fiscal_database))
            self.domestic_pending = FiscalDomesticPendingQueue(str(fiscal_database))

            self.ecosystem_service = EcosystemService(
                decision_store=DecisionStore(str(self.runtime_dir / "decision-memory.sqlite3"))
            )
            self.conversation_store = AssistantConversationStore(
                self.runtime_dir / "assistant-conversations.sqlite3"
            )
            self.assistant = EcosystemAssistant(
                store=self.conversation_store,
                service=self.ecosystem_service,
                fiscal=self.fiscal_reserve,
                fiscal_pending_queue=self.foreign_pending,
                fiscal_domestic_pending_queue=self.domestic_pending,
            )
            self.application = build_standalone_application(
                ecosystem_service=self.ecosystem_service,
                fiscal_reserve=self.fiscal_reserve,
                fiscal_owner_id=self.fiscal_owner_id,
                foreign_pending=self.foreign_pending,
                domestic_pending=self.domestic_pending,
                assistant=self.assistant,
                trusted_identity=configured_identity,
            )
        except Exception:
            self.process_lock.release()
            self.closed = True
            raise

    @classmethod
    def from_environment(cls) -> "StandaloneRuntime":
        return cls()

    def close(self) -> None:
        if self.closed:
            return
        self.process_lock.release()
        self.closed = True

    def __enter__(self) -> "StandaloneRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
