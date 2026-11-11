from __future__ import annotations

import io
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app as app_module
from app import application


def request(path: str, *, identity: str | None = None, query: str = ""):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
        "REMOTE_ADDR": "198.51.100.25",
        "HTTP_HOST": "control.example.test",
        "wsgi.url_scheme": "https",
    }
    if identity is not None:
        environ["HTTP_X_AUTHENTICATED_USER"] = identity
    body = b"".join(application(environ, start_response))
    return captured["status"], captured["headers"], json.loads(body)


@pytest.fixture
def remote_identity_required(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "true")
    monkeypatch.setenv("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "X-Authenticated-User")
    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "owner@example.test")


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/status",
        "/api/memory",
        "/api/journal",
        "/api/statistics",
        "/api/preferences",
        "/api/notifications",
        "/api/notifications/all",
        "/api/risk",
        "/api/connections",
        "/api/learning",
        "/api/learning/resources",
        "/api/learning/sources",
        "/api/learning/observations",
        "/api/learning/activities",
        "/api/security/audit",
        "/api/assistant/local/status",
        "/api/assistant/status",
        "/api/assistant/conversations",
        "/api/assistant/history",
        "/api/fiscal-reserve/local",
        "/api/fiscal-reserve",
        "/api/fiscal-reserve/pending",
        "/api/fiscal-reserve/domestic-pending",
        "/api/fiscal-reserve/domestic-pending/summary",
        "/api/fiscal-reserve/mt5-preview",
        "/api/onboarding",
        "/api/notifications/recovery/inspect",
        "/api/saas/status",
        "/api/runtime/real/status",
        "/api/runtime/timed-exits",
        "/api/runtime/positions/recovery/local",
        "/api/runtime/positions/recovery",
        "/api/runtime/analysis/latest",
        "/api/market/assets",
        "/api/reports",
    ],
)
def test_remote_private_get_routes_reject_missing_identity(path, remote_identity_required):
    status, _, payload = request(path)

    assert status == "401 Unauthorized"
    assert "Identidade autenticada necessária" in payload["error"]


def test_remote_private_get_route_rejects_wrong_identity(remote_identity_required):
    status, _, payload = request("/api/risk", identity="other@example.test")

    assert status == "403 Forbidden"
    assert "Identidade autenticada necessária" in payload["error"]


def test_remote_private_get_route_accepts_pinned_identity(remote_identity_required):
    status, _, payload = request("/api/risk", identity="owner@example.test")

    assert status == "200 OK"
    assert isinstance(payload["allowed"], bool)


def test_remote_liveness_probe_remains_public(remote_identity_required):
    status, _, payload = request("/api/health/live")

    assert status == "200 OK"
    assert payload == {"ok": True, "live": True, "service": "controlador"}



def test_journal_returns_persistent_operational_records_for_sao_paulo_day(monkeypatch, remote_identity_required):
    timezone = ZoneInfo("America/Sao_Paulo")
    current = datetime(2026, 11, 11, 10, 30, tzinfo=timezone)
    previous_day = datetime(2026, 11, 10, 23, 59, tzinfo=timezone)
    current_record = SimpleNamespace(
        timestamp=current,
        signal=SimpleNamespace(value="COMPRA"),
        score=86.0,
        decision="EXECUTAR",
        reason="Condições confirmadas",
        result="WIN",
        symbol="WINZ26",
        timeframe="M5",
        quality_score=91.0,
        quality_level="FORTE",
        entry_conditions=("estrutura confirmada",),
    )
    previous_record = SimpleNamespace(
        timestamp=previous_day,
        signal=SimpleNamespace(value="VENDA"),
        score=72.0,
        decision="AGUARDAR",
        reason="Fora do contexto",
        result="PENDENTE",
        symbol="WINZ26",
        timeframe="M5",
        quality_score=70.0,
        quality_level="MODERADA",
        entry_conditions=(),
    )
    memory = SimpleNamespace(records=lambda: (previous_record, current_record))
    runtime = SimpleNamespace(operational_recorder=SimpleNamespace(memory=memory))
    monkeypatch.setattr(app_module.SERVICE, "operational_runtime", runtime)

    status, _, payload = request(
        "/api/journal",
        identity="owner@example.test",
        query="date=2026-11-11&limit=10",
    )

    assert status == "200 OK"
    assert payload["source"] == "persistent_operational_runtime_memory"
    assert payload["timezone"] == "America/Sao_Paulo"
    assert payload["read_only"] is True
    assert payload["execution_allowed"] is False
    assert payload["count"] == 1
    assert payload["entries"][0]["signal"] == "COMPRA"
    assert payload["today_summary"] == {
        "date": "2026-11-11",
        "total": 1,
        "win": 1,
        "loss": 0,
        "ambos": 0,
        "pending": 0,
    }


def test_journal_fails_closed_when_operational_memory_is_unavailable(monkeypatch, remote_identity_required):
    monkeypatch.setattr(app_module.SERVICE, "operational_runtime", None)

    status, _, payload = request("/api/journal", identity="owner@example.test")

    assert status == "503 Service Unavailable"
    assert payload["entries"] == []
    assert payload["execution_allowed"] is False


def test_journal_rejects_invalid_date(remote_identity_required):
    status, _, payload = request(
        "/api/journal",
        identity="owner@example.test",
        query="date=not-a-date",
    )

    assert status == "400 Bad Request"
    assert "YYYY-MM-DD" in payload["error"]
