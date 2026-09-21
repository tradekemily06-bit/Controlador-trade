from __future__ import annotations

import os

import pytest

from core.safe_file import read_regular_utf8


def test_read_regular_utf8_reads_through_descriptor(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"ok": true}', encoding="utf-8")

    assert read_regular_utf8(path, max_bytes=1024) == '{"ok": true}'


def test_read_regular_utf8_rejects_symlink(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("secret", encoding="utf-8")
    link = tmp_path / "state.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(OSError):
        read_regular_utf8(link, max_bytes=1024)


def test_read_regular_utf8_enforces_open_descriptor_size(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("0123456789", encoding="utf-8")

    with pytest.raises(ValueError):
        read_regular_utf8(path, max_bytes=5)


def test_read_regular_utf8_rejects_directory(tmp_path):
    path = tmp_path / "state"
    path.mkdir()

    with pytest.raises(OSError):
        read_regular_utf8(path, max_bytes=1024)


def test_read_regular_utf8_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "state"
    path.write_bytes(b"\\xff")

    with pytest.raises(UnicodeDecodeError):
        read_regular_utf8(path, max_bytes=1024)
