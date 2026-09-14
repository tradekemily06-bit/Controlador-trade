import io
import json

from app import application


def call_app(path):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": "GET",
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
    }
    result = b"".join(application(environ, start_response))
    return captured["status"], json.loads(result)


def test_onboarding_endpoint_exposes_guided_first_use_without_execution_authority():
    status, payload = call_app("/api/onboarding")

    assert status == "200 OK"
    guide = payload["guide"]
    assert guide["guide_id"] == "first-use"
    assert guide["execution_authorized"] is False
    assert [step["location"] for step in guide["steps"]] == [
        "OPERATION",
        "ANALYSIS",
        "RISK",
        "LEARNING",
        "MEMORY",
        "HISTORY",
        "CONNECTIONS",
        "SECURITY",
        "SETTINGS",
        "HELP",
    ]
    assert all(step["technical_details_hidden"] is True for step in guide["steps"])
