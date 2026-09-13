import io
import json

from app import application


def request(path, method="GET", payload=None):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "REMOTE_ADDR": "127.0.0.1",
    }
    result = b"".join(application(environ, start_response))
    return captured["status"], json.loads(result)


def test_learning_resource_and_observation_are_available_without_execution_authority():
    status, payload = request(
        "/api/learning/resources",
        "POST",
        {
            "resource_id": "res-test",
            "title": "Material de teste",
            "content_type": "VIDEO",
            "source_url": "https://example.com/material",
            "tags": ["pavio", "contexto"],
        },
    )
    assert status.startswith("200")
    assert payload["resource"]["content_type"] == "VIDEO"
    assert payload["execution_allowed"] is False

    status, payload = request(
        "/api/learning/observations",
        "POST",
        {
            "resource_id": "res-test",
            "statement": "Observação educacional",
            "concepts": ["pavio"],
            "confidence": 0.8,
        },
    )
    assert status.startswith("200")
    assert payload["learning_authorizes_trading"] is False
    assert payload["execution_allowed"] is False


def test_learning_activity_requires_no_trade_permission():
    status, payload = request(
        "/api/learning/activities",
        "POST",
        {
            "activity_id": "activity-test",
            "prompt": "Identifique o contexto da vela.",
            "expected_concepts": ["contexto"],
        },
    )
    assert status.startswith("200")
    assert payload["execution_allowed"] is False

    status, payload = request(
        "/api/learning/attempts",
        "POST",
        {"activity_id": "activity-test", "answer": "Contexto de teste", "correct": True},
    )
    assert status.startswith("200")
    assert payload["execution_allowed"] is False
