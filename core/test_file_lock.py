import os

import pytest

from core.file_lock import exclusive_file_lock


def test_lock_creates_restricted_lock_file(tmp_path):
    lock = tmp_path / "state.lock"
    with exclusive_file_lock(lock):
        assert lock.exists()
        assert (lock.stat().st_mode & 0o077) == 0


def test_lock_rejects_symlink_when_platform_supports_no_follow(tmp_path):
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("platform has no O_NOFOLLOW")
    target = tmp_path / "target"
    target.write_text("sentinel", encoding="utf-8")
    lock = tmp_path / "state.lock"
    lock.symlink_to(target)
    with pytest.raises(RuntimeError, match="lock operacional"):
        with exclusive_file_lock(lock):
            pass
    assert target.read_text(encoding="utf-8") == "sentinel"
