from __future__ import annotations

import pytest

from analysis.decision_store import DecisionStore


def test_decision_store_rejects_symlink_database(tmp_path):
    target = tmp_path / "real.sqlite"
    target.write_bytes(b"not-a-database")
    link = tmp_path / "decisions.sqlite"
    link.symlink_to(target)
    with pytest.raises(RuntimeError):
        DecisionStore(str(link))


def test_decision_store_rejects_symlinked_database_directory(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    linked_dir = tmp_path / "linked"
    linked_dir.symlink_to(real_dir, target_is_directory=True)
    with pytest.raises(RuntimeError):
        DecisionStore(str(linked_dir / "decisions.sqlite"))
