from __future__ import annotations

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


def test_query_limit_rejects_oversized_query_string():
    from app import MAX_QUERY_STRING_BYTES
    with pytest.raises(ValueError, match="query string"):
        _query_limit(_environ("x=" + "a" * MAX_QUERY_STRING_BYTES), 10, maximum=100)


def test_replay_workload_limit_is_explicit():
    from app import MAX_REPLAY_CASES
    assert MAX_REPLAY_CASES == 100


def test_query_limit_rejects_excessive_parameter_count():
    with pytest.raises(ValueError):
        _query_limit(_environ("&".join(f"x{i}=1" for i in range(257))), 10, maximum=100)


def test_read_json_rejects_deep_recursion_as_invalid_input():
    from app import _read_json
    nested = "[" * 2000 + "0" + "]" * 2000
    environ = {"CONTENT_LENGTH": str(len(nested.encode("utf-8"))), "wsgi.input": __import__("io").BytesIO(nested.encode("utf-8"))}
    with pytest.raises(ValueError, match="JSON inválido"):
        _read_json(environ)
