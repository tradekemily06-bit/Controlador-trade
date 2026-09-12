from io import BytesIO
from json import loads

from app import application


def _call(path, method="GET", body=b""):
    status = []
    headers = []

    def start_response(value, response_headers):
        status.append(value)
        headers.extend(response_headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path.split("?", 1)[0],
        "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "REMOTE_ADDR": "127.0.0.1",
        "wsgi.input": BytesIO(body),
    }
    payload = b"".join(application(environ, start_response))
    return status[0], dict(headers), payload


def test_final_health_status_is_safe_and_operational():
    status, _, body = _call("/api/health")
    data = loads(body)
    assert status == "200 OK"
    assert data["ok"] is True
    assert data["decision_engine"] == "ONLINE"
    assert data["risk_gate"] == "ONLINE"
    assert data["mt5_demo"] == "DEMO_VALIDADO"
    assert data["real"] == "DESABILITADO"
    assert data["execution_allowed"] is False


def test_final_api_flow_analyze_outcome_statistics():
    status, _, body = _call(
        "/api/analyze",
        "POST",
        b'{"score":85,"confirmed":true,"filters_ok":true,"symbol":"EURUSD","timeframe":"5m"}',
    )
    data = loads(body)
    assert status == "200 OK"
    assert data["signal"] in {"COMPRA", "VENDA", "AGUARDAR"}
    assert data["execution_allowed"] is False
    decision_id = data["decision_id"]

    status, _, body = _call(
        "/api/outcome",
        "POST",
        (f'{{"decision_id":"{decision_id}","outcome":"WIN"}}').encode(),
    )
    assert status == "200 OK"
    assert loads(body)["outcome"] == "WIN"

    status, _, body = _call("/api/statistics")
    assert status == "200 OK"
    assert loads(body)["wins"] >= 1


def test_final_api_read_surfaces_and_mobile_shell():
    for path in (
        "/api/status",
        "/api/memory?limit=8",
        "/api/risk",
        "/api/news?limit=8",
        "/api/connections",
        "/api/saas/status",
        "/manifest.webmanifest",
    ):
        status, _, _ = _call(path)
        assert status == "200 OK"

    status, headers, body = _call("/")
    html = body.decode("utf-8")
    assert status == "200 OK"
    assert "REAL BLOQUEADO" in html
    assert 'name="viewport"' in html
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert "nonce-" in headers["Content-Security-Policy"]
    assert "nonce=\"" in html


def test_final_api_has_no_live_execution_route():
    status, _, body = _call("/api/execute", "POST", b"{}")
    assert status == "404 Not Found"
    assert body == b"Not Found"
