"""Pytest-only isolation for modules that initialize the application at import time.

Production startup still requires an explicitly configured single-user identity.
The test suite supplies a disposable identity and runtime directory before test
modules import app.py, preventing writes to a developer's real .runtime data.
"""
import os
import tempfile

_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="controlador-trade-pytest-")
os.environ.setdefault("CONTROLADOR_RUNTIME_DIR", _TEST_RUNTIME.name)
os.environ.setdefault("CONTROLADOR_SINGLE_USER_IDENTITY", "pytest-single-user")
