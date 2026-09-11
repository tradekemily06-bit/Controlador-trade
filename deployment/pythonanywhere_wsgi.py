"""WSGI entry point for PythonAnywhere."""

import sys
from pathlib import Path

PROJECT_ROOT = Path.home() / "Controlador-trade"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import application
