from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

# High-confidence credential formats only. This intentionally avoids broad
# password/API-key heuristics that would flag ordinary test fixtures.
_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
)

_SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv"}


def test_tracked_text_contains_no_high_confidence_secret_literal():
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in _PATTERNS:
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")
    assert findings == [], "High-confidence credential literal found in tracked repository text: " + "; ".join(findings)
