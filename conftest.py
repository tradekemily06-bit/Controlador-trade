"""Pytest-only isolation for modules that initialize the application at import time.

Production startup still requires an explicitly configured single-user identity.
Tests always use a disposable runtime directory, identity, and SQLite paths so
collection cannot read or mutate a developer's real runtime data.
"""
import os
import tempfile
from pathlib import Path

_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="controlador-trade-pytest-")
_TEST_RUNTIME_PATH = Path(_TEST_RUNTIME.name)

# Deliberately override inherited machine/CI values: tests must never attach to
# a developer's or deployed runtime, even when those variables are exported.
os.environ["CONTROLADOR_RUNTIME_DIR"] = str(_TEST_RUNTIME_PATH)
os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "pytest-single-user"
os.environ["CONTROLADOR_DECISION_DB"] = str(_TEST_RUNTIME_PATH / "decision-memory.sqlite")
os.environ["CONTROLADOR_FISCAL_RESERVE_DB"] = str(_TEST_RUNTIME_PATH / "fiscal-reserve.sqlite3")
os.environ["CONTROLADOR_ASSISTANT_DB"] = str(_TEST_RUNTIME_PATH / "assistant.sqlite3")
os.environ["CONTROLADOR_SECURITY_AUDIT_DB"] = str(_TEST_RUNTIME_PATH / "security-audit.sqlite")
