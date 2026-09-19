from __future__ import annotations

import io

import pytest

from app import _query_limit


def _environ(query: str):
    return {"QUERY_STRING": query}


def test_query_limit_enforces_maximum():
    assert _query_limit(_environ("limit=100"), 10, maximum=100) == 100
    with pytest.raises(ValueError, match="fora do limite"):
        _query_limit(_environ("limit=101"), 10, maximum=100)


def test_query_limit_rejects_invalid_default_and_maximum():
    with pytest.raises(ValueError):
        _query_limit(_environ(""), 101, maximum=100)
    with pytest.raises(ValueError):
        _query_limit(_environ(""), 10, maximum=0)
