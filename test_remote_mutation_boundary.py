import io
import json

from app import application


def test_remote_api_mutation_is_blocked_without_trusted_identity():
    payload = json.dumps({"score": 90, "symbol": "EURUSD", "timeframe": "5m"}).encode()
    captured = {}

    def start_response(status, headers):
        captured["status"] = status

    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/analyze",
        "QUERY_STRING": "",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(payload)),
        "REMOTE_ADDR": "192.0.2.10",
        "wsgi.input": io.BytesIO(payload),
    }
    body = b"".join(application(environ, start_response))
    assert captured["status"] == "403 Forbidden"
    assert "identidade confiável" in body.decode("utf-8")
