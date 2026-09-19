from pathlib import Path

import pytest

from core.durable_json import locked_path


def test_locked_path_rejects_symlinked_lock_file(tmp_path: Path):
    if not hasattr(__import__("os"), "O_NOFOLLOW"):
        pytest.skip("O_NOFOLLOW indisponível neste sistema")

    state = tmp_path / "state.json"
    lock = tmp_path / ".state.json.lock"
    target = tmp_path / "attacker-target"
    target.write_text("do not touch", encoding="utf-8")
    lock.symlink_to(target)

    with pytest.raises(OSError):
        with locked_path(state):
            pass

    assert target.read_text(encoding="utf-8") == "do not touch"
