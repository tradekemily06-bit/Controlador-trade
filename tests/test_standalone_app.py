from __future__ import annotations

import base64
import io
import types
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from standalone_app import StandaloneWSGIApplication, _runtime_from_environment, _validate_bind_security
from integration.standalone_runtime import StandaloneRuntime
from analysis.decision_record import DecisionRecord
from security.push_subscription_registry import TenantPushSubscriptionRegistry


class FakeRuntime:
    closed = False

    class Application:
        def architecture(self):
            return {
                "architecture": "ONE_SHARED_INTELLIGENCE",
                "application_areas": [{"name": str(i)} for i in range(6)],
                "area_handler_status": {},
            }

        def handle(self, *, area, task, context=None):
            return {
                "area": area,
                "task": task,
                "status": "NOT_CONNECTED",
                "execution_authorized": False,
            }

    application = Application()

    class EcosystemService:
        def notification_items(self, *, include_info=False):
            return [{"notification_id": "n1", "title": "Sinal atualizado"}]

        def notification_summary(self):
            return {"total": 1, "external_delivery": "OUTBOX_ONLY_NO_PROVIDER"}

    ecosystem_service = EcosystemService()
    notification_worker = None
    backup_scheduler = None

    class TenantState:
        def __init__(self):
            self.preferences = {}
            self.notifications = {}

        def load_preferences(self, context):
            return self.preferences.get(context.key)

        def save_preferences(self, context, preferences):
            self.preferences[context.key] = dict(preferences)

        def load_notifications(self, context):
            return list(self.notifications.get(context.key, []))

        def save_notifications(self, context, notifications):
            self.notifications[context.key] = list(notifications)

        def readiness(self):
            return {
                "status": "LOCAL_TENANT_SCOPED_STORAGE",
                "production_ready": False,
            }

    tenant_state = TenantState()

    class TenantDecisionMemory:
        def __init__(self):
            self.contexts = []
            self.records = []

        def readiness(self):
            return {"status": "LOCAL_TENANT_SCOPED_DECISION_MEMORY", "production_ready": False}

        def load(self, context, *, limit=100):
            self.contexts.append(context)
            return self.records[-limit:]

    tenant_decision_memory = TenantDecisionMemory()
    fiscal_owner_id = "local-fiscal-owner"

    class Assistant:
        def __init__(self):
            self.calls = []
            self.owners = {}

        def conversations(self, identity):
            self.calls.append(("list", identity))
            return [{"conversation_id": item} for item in self.owners.get(identity, [])]

        def history(self, identity, conversation_id):
            self.calls.append(("history", identity, conversation_id))
            if conversation_id not in self.owners.get(identity, []):
                raise PermissionError("conversa não encontrada")
            return [{"role": "user", "content": "privado"}]

        def delete_conversation(self, identity, conversation_id):
            self.calls.append(("delete", identity, conversation_id))
            if conversation_id not in self.owners.get(identity, []):
                raise PermissionError("conversa não encontrada")
            self.owners[identity].remove(conversation_id)
            return True

        def ask(self, **kwargs):
            self.calls.append(("ask", kwargs))
            return {"conversation_id": "new-conversation", "answer": "Resposta", "read_only": True, "execution_allowed": False}

    assistant = Assistant()

    class MarketMonitor:
        def __init__(self):
            self.calls = []

        def status(self, context=None):
            if context is not None:
                self.calls.append(("status", context.tenant_id, context.subject_id))
            return {"enabled": 0, "total": 0, "worker_running": False, "subscriptions": [], "execution_authorized": False}

        def latest_results(self, limit=50, *, context):
            self.calls.append(("results", context.tenant_id, context.subject_id))
            return []

        def subscriptions(self, context):
            self.calls.append(("subscriptions", context.tenant_id, context.subject_id))
            return []

        def subscribe(self, symbol, timeframe, *, context):
            self.calls.append(("subscribe", context.tenant_id, context.subject_id))
            return {"symbol": symbol, "timeframe": timeframe, "enabled": True}

        def unsubscribe(self, symbol, timeframe, *, context):
            self.calls.append(("unsubscribe", context.tenant_id, context.subject_id))
            return True

    market_monitor = MarketMonitor()


def call_wsgi(app, path, method="GET", body=None, remote_addr="127.0.0.1", origin=None, include_headers=False, authorization=None, identity_verified=False, remote_user=None, tenant_id=None, scheme="http"):
    raw = json.dumps(body or {}).encode("utf-8")
    parsed_path = urlsplit(path)
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": parsed_path.path,
        "QUERY_STRING": parsed_path.query,
        "REMOTE_ADDR": remote_addr,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
        "wsgi.url_scheme": scheme,
    }
    if origin is not None:
        environ["HTTP_ORIGIN"] = origin
    if authorization is not None:
        environ["HTTP_AUTHORIZATION"] = authorization
    if identity_verified:
        environ["controlador.identity_verified"] = True
    if remote_user is not None:
        environ["REMOTE_USER"] = remote_user
    if tenant_id is not None:
        environ["controlador.tenant_id"] = tenant_id
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    response = b"".join(app(environ, start_response))
    decoded = json.loads(response.decode("utf-8")) if response else {}
    result = (captured["status"], decoded)
    return (*result, captured["headers"]) if include_headers else result


class StandaloneWSGITests(unittest.TestCase):
    def test_market_data_provider_status_is_visible_to_local_operator(self):
        class Registry:
            def status(self, *, probe_account_mode=True):
                return {
                    "selected_provider": "mt5_relay",
                    "providers": [
                        {"provider_id": "mt5_relay", "status": "CONNECTED", "selected": True}
                    ],
                    "count": 1,
                    "provider_registered": True,
                }

        class Connections:
            def list_connections(self, context):
                assert context.tenant_id == "local-single-user"
                assert context.subject_id == "local-owner"
                return []

        runtime = FakeRuntime()
        runtime.market_data_registry = Registry()
        runtime.tenant_provider_connections = Connections()
        app = StandaloneWSGIApplication(runtime)
        settings = {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(app, "/api/market-data/providers")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["providers"][0]["provider_id"], "mt5_relay")
        self.assertEqual(body["scope"], "LOCAL_SINGLE_USER")
        self.assertEqual(body["connections"], [])
        self.assertFalse(body["execution_authorized"])

    def test_market_data_provider_status_does_not_leak_global_connections_to_remote_users(self):
        class Registry:
            def status(self, *, probe_account_mode=True):
                raise AssertionError("global provider status must not be exposed")

        runtime = FakeRuntime()
        runtime.market_data_registry = Registry()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/market-data/providers",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["status"], "USER_SCOPED_PROVIDER_CONNECTIONS_NOT_CONFIGURED")
        self.assertEqual(body["connections"], [])
        self.assertEqual(body["count"], 0)
        self.assertNotIn("providers", body)
        self.assertFalse(body["execution_authorized"])


    def test_remote_market_data_provider_status_uses_only_verified_tenant_connections(self):
        class Connections:
            def list_connections(self, context):
                assert context.tenant_id == "tenant-a"
                assert context.subject_id == "alice"
                return [{
                    "connection_id": "a" * 32,
                    "provider_id": "broker_x",
                    "account_alias": "Conta Alice",
                    "account_reference": "account-a",
                    "status": "CONNECTED",
                    "last_verified_at": "2026-11-26T12:00:00+00:00",
                    "capabilities": ["candles:read"],
                    "read_only": True,
                    "execution_authorized": False,
                }]

        runtime = FakeRuntime()
        runtime.tenant_provider_connections = Connections()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/market-data/providers",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "TENANT_AND_SUBJECT")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["connections"][0]["provider_id"], "broker_x")
        self.assertNotIn("configured_data_sources", body)
        self.assertFalse(body["execution_authorized"])

    def test_assistant_status_reports_conversation_scope_and_remote_chat_guard(self):
        runtime = FakeRuntime()
        runtime.assistant = FakeRuntime.Assistant()
        runtime.assistant.readiness = lambda: {"available": True, "status": "CONFIGURED_NOT_TESTED"}
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/assistant/status",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["conversation_scope"], "TENANT_AND_SUBJECT")
        self.assertEqual(body["remote_chat"], "TENANT_SCOPED_FISCAL_CONTEXT")
        self.assertTrue(body["tenant_context_available"])
        self.assertFalse(body["execution_authorized"])

    def test_assistant_conversations_are_scoped_to_verified_tenant_and_subject(self):
        runtime = FakeRuntime()
        runtime.assistant = FakeRuntime.Assistant()
        runtime.assistant.owners["tenant:tenant-a:subject:alice"] = ["alice-conversation"]
        runtime.assistant.owners["tenant:tenant-b:subject:bob"] = ["bob-conversation"]
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status_a, body_a = call_wsgi(
                app, "/api/assistant/conversations",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            status_b, body_b = call_wsgi(
                app, "/api/assistant/conversations",
                remote_addr="203.0.113.11",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-b",
            )
        self.assertEqual(status_a, "200 OK")
        self.assertEqual(body_a["conversations"][0]["conversation_id"], "alice-conversation")
        self.assertEqual(status_b, "200 OK")
        self.assertEqual(body_b["conversations"][0]["conversation_id"], "bob-conversation")
        self.assertEqual(runtime.assistant.calls[0][1], "tenant:tenant-a:subject:alice")
        self.assertEqual(runtime.assistant.calls[1][1], "tenant:tenant-b:subject:bob")

    def test_assistant_history_and_delete_cannot_cross_owner_boundary(self):
        runtime = FakeRuntime()
        runtime.assistant = FakeRuntime.Assistant()
        runtime.assistant.owners["tenant:tenant-a:subject:alice"] = ["alice-conversation"]
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/assistant/conversations/history?conversation_id=alice-conversation",
                remote_addr="203.0.113.11",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-b",
            )
            delete_status, delete_body = call_wsgi(
                app, "/api/assistant/conversations", method="DELETE",
                body={"conversation_id": "alice-conversation"},
                remote_addr="203.0.113.11",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-b",
            )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(delete_status, "404 Not Found")
        self.assertFalse(delete_body.get("deleted", False))
        self.assertEqual(runtime.assistant.owners["tenant:tenant-a:subject:alice"], ["alice-conversation"])

    def test_local_assistant_ask_uses_local_tenant_context_and_fiscal_owner(self):
        runtime = FakeRuntime()
        runtime.assistant = FakeRuntime.Assistant()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app, "/api/assistant/ask", method="POST",
                body={"message": "Explique meu resumo fiscal"},
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "LOCAL_SINGLE_USER")
        self.assertFalse(body["execution_authorized"])
        call = runtime.assistant.calls[0][1]
        self.assertEqual(call["identity"], "tenant:local-single-user:subject:local-owner")
        self.assertEqual(call["fiscal_owner_id"], "local-fiscal-owner")
        self.assertEqual(call["message"], "Explique meu resumo fiscal")

    def test_remote_assistant_ask_is_blocked_until_fiscal_storage_is_tenant_scoped(self):
        runtime = FakeRuntime()
        runtime.assistant = FakeRuntime.Assistant()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/assistant/ask", method="POST",
                body={"message": "Consulte meus dados fiscais"},
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(body["state"], "FISCAL_TENANT_ISOLATION_REQUIRED")
        self.assertEqual(runtime.assistant.calls, [])

    def test_local_fiscal_summary_api_returns_owner_bound_read_only_data(self):
        runtime = FakeRuntime()

        class FiscalReserve:
            def __init__(self):
                self.calls = []

            def summary(self, owner_id, *, history_limit, history_offset):
                self.calls.append((owner_id, history_limit, history_offset))
                return {
                    "name": "Reserva Fiscal",
                    "total_reserved_brl": 125.50,
                    "history": [],
                    "reserve_semantics": {"kind": "PLANNING_ESTIMATE_ONLY"},
                }

        runtime.fiscal_reserve = FiscalReserve()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(app, "/api/fiscal/summary?limit=25&offset=10")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "LOCAL_SINGLE_USER")
        self.assertEqual(body["summary"]["total_reserved_brl"], 125.50)
        self.assertFalse(body["tax_assessment"])
        self.assertFalse(body["money_movement"])
        self.assertFalse(body["execution_authorized"])
        self.assertEqual(runtime.fiscal_reserve.calls, [("local-fiscal-owner", 25, 10)])

    def test_remote_fiscal_summary_never_reads_legacy_single_owner_database(self):
        runtime = FakeRuntime()

        class FiscalReserve:
            def __init__(self):
                self.called = False

            def summary(self, *args, **kwargs):
                self.called = True
                raise AssertionError("legacy shared fiscal database must not be read remotely")

        runtime.fiscal_reserve = FiscalReserve()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/fiscal/summary",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(body["state"], "FISCAL_REMOTE_STORAGE_NOT_READY")
        self.assertFalse(runtime.fiscal_reserve.called)
        self.assertFalse(body["execution_authorized"])

    def test_fiscal_summary_rejects_invalid_pagination(self):
        runtime = FakeRuntime()

        class FiscalReserve:
            def summary(self, *args, **kwargs):
                raise AssertionError("invalid pagination must be rejected before repository access")

        runtime.fiscal_reserve = FiscalReserve()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(app, "/api/fiscal/summary?limit=0")
        self.assertEqual(status, "400 Bad Request")
        self.assertFalse(body["execution_authorized"])

    def test_health_exposes_one_intelligence_and_six_visible_areas(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/health")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["architecture"], "ONE_SHARED_INTELLIGENCE")
        self.assertEqual(body["areas"], 6)
        self.assertFalse(body["execution_authorized"])

    def test_readiness_endpoint_reports_unconfigured_services_without_claiming_live(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/readiness")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["areas"], 6)
        self.assertEqual(body["market_data"]["status"], "NOT_CONFIGURED")
        self.assertEqual(body["news"]["status"], "NOT_CONFIGURED")
        self.assertEqual(body["decision_memory"]["state"], "STATUS_NOT_EXPOSED")
        self.assertFalse(body["decision_memory"]["durability_confirmed"])
        self.assertEqual(body["notification_delivery"]["state"], "NO_EXTERNAL_SINK_CONFIGURED")
        self.assertEqual(body["deployment"], "PROCESS_RUNNING_DEPLOYMENT_NOT_VERIFIED")
        self.assertEqual(
            body["deployment_topology"],
            {"deployment_topology": "UNKNOWN", "multi_replica_ready": False},
        )
        self.assertEqual(body["identity"]["trusted_identity_provider"], "NOT_CONFIGURED")
        self.assertEqual(body["tenant_state"]["status"], "LOCAL_TENANT_SCOPED_STORAGE")
        self.assertFalse(body["tenant_state"]["production_ready"])
        self.assertEqual(body["tenant_decision_memory"]["status"], "LOCAL_TENANT_SCOPED_DECISION_MEMORY")
        self.assertFalse(body["tenant_decision_memory"]["production_ready"])
        self.assertEqual(body["tenant_fiscal_storage"]["status"], "NOT_CONFIGURED")
        self.assertFalse(body["tenant_fiscal_storage"]["production_ready"])
        self.assertEqual(body["identity"]["multi_tenant_isolation"], "SINGLE_USER_RUNTIME_ONLY")
        self.assertFalse(body["identity"]["shared_bearer_token_is_user_identity"])
        self.assertFalse(body["backup_scheduler"]["enabled"])
        self.assertEqual(body["backup_scheduler"]["status"], "NOT_CONFIGURED")
        self.assertFalse(body["execution_authorized"])

    def test_local_readiness_reports_provider_recovery_without_secret_material(self):
        runtime = FakeRuntime()
        runtime.ctrader_recovery_status = [
            {
                "connection_id": "c" * 32,
                "provider_id": "ctrader_open_api",
                "status": "RECONNECT_FAILED",
                "error_class": "PermissionError",
                "token": "must-not-leak",
                "execution_authorized": False,
            },
        ]
        runtime.provider_recovery_status = [
            {
                "connection_id": "a" * 32,
                "provider_id": "broker_a",
                "status": "RECONNECT_FAILED",
                "error_class": "PermissionError",
                "credential_ref": "vault://must-not-leak",
                "secret": "must-not-leak",
                "execution_authorized": False,
            },
            {
                "connection_id": "b" * 32,
                "provider_id": "broker_b",
                "status": "RECONNECTED",
                "adapter_status": "ADAPTER_BOUND",
                "execution_authorized": False,
            },
        ]
        app = StandaloneWSGIApplication(runtime)
        status, body = call_wsgi(app, "/api/readiness")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["provider_recovery"]["status"], "DEGRADED")
        self.assertEqual(len(body["provider_recovery"]["accounts"]), 2)
        serialized = json.dumps(body["provider_recovery"])
        self.assertNotIn("vault://must-not-leak", serialized)
        self.assertNotIn("must-not-leak", serialized)
        self.assertFalse(body["provider_recovery"]["execution_authorized"])
        self.assertEqual(body["ctrader_recovery"]["status"], "DEGRADED")
        self.assertEqual(len(body["ctrader_recovery"]["accounts"]), 1)
        self.assertNotIn("must-not-leak", json.dumps(body["ctrader_recovery"]))
        self.assertFalse(body["ctrader_recovery"]["execution_authorized"])

    def test_backup_status_endpoint_never_claims_unconfigured_backup_or_replication(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/backup/status")
        self.assertEqual(status, "200 OK")
        self.assertFalse(body["enabled"])
        self.assertFalse(body["worker_running"])
        self.assertEqual(body["status"], "NOT_CONFIGURED")
        self.assertEqual(body["off_host_replication"], "NOT_CONFIGURED")
        self.assertFalse(body["execution_authorized"])

    def test_backup_status_endpoint_reports_injected_scheduler(self):
        runtime = FakeRuntime()
        class Scheduler:
            def status(self):
                return {
                    "enabled": True,
                    "worker_running": True,
                    "last_status": "SUCCESS",
                    "off_host_replication": "NOT_CONFIGURED",
                    "execution_authorized": False,
                }
        runtime.backup_scheduler = Scheduler()
        status, body = call_wsgi(StandaloneWSGIApplication(runtime), "/api/backup/status")
        self.assertEqual(status, "200 OK")
        self.assertTrue(body["enabled"])
        self.assertTrue(body["worker_running"])
        self.assertEqual(body["last_status"], "SUCCESS")
        self.assertFalse(body["execution_authorized"])

    def test_timeframe_catalog_exposes_supported_intervals_and_limits(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/market-data/timeframes")
        self.assertEqual(status, "200 OK")
        self.assertIn("1m", body["canonical"])
        self.assertIn("10m", body["canonical"])
        self.assertIn("M1", body["platform"])
        self.assertIn("M10", body["platform"])
        self.assertIn("M59", body["platform"])
        self.assertIn("H24", body["platform"])
        self.assertIn("D31", body["platform"])
        self.assertIn("W4", body["platform"])
        self.assertNotIn("MN1", body["platform"])
        self.assertIn("months", body["excluded"])
        self.assertEqual(body["parser_support"], "NORMALIZATION_ONLY")
        self.assertEqual(body["provider_compatibility"]["status"], "NO_PROVIDER_SELECTED")
        self.assertFalse(body["execution_authorized"])

    def test_architecture_endpoint_is_read_only(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/intelligence/architecture")
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(body["application_areas"]), 6)

    def test_unknown_order_endpoint_does_not_exist(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/orders", method="POST", body={"symbol": "EURUSD"})
        self.assertEqual(status, "404 Not Found")
        self.assertFalse(body["execution_authorized"])

    def test_notifications_endpoint_returns_local_single_user_inbox(self):
        runtime = FakeRuntime()
        runtime.tenant_state = FakeRuntime.TenantState()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(app, "/api/notifications?limit=10")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "LOCAL_SINGLE_USER")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["notifications"][0]["notification_id"], "n1")
        self.assertFalse(body["execution_authorized"])

    def test_local_notifications_merge_explicitly_addressed_market_events(self):
        runtime = FakeRuntime()
        runtime.tenant_state.notifications = {
            "tenant:local-single-user:subject:local-owner": [
                {"notification_id": "market-1", "title": "Mudança de sinal"}
            ]
        }
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(app, "/api/notifications?limit=10")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "LOCAL_SINGLE_USER")
        ids = [item["notification_id"] for item in body["notifications"]]
        self.assertEqual(ids, ["n1", "market-1"])
        self.assertFalse(body["execution_authorized"])

    def test_local_decision_memory_endpoint_uses_configured_single_user_scope(self):
        runtime = FakeRuntime()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(app, "/api/memory/decisions?limit=25")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["decisions"], [])
        self.assertEqual(body["scope"], "TENANT_SCOPED")
        self.assertEqual(runtime.tenant_decision_memory.contexts[0].tenant_id, "local-single-user")
        self.assertEqual(runtime.tenant_decision_memory.contexts[0].subject_id, "local-owner")
        self.assertFalse(body["execution_authorized"])

    def test_remote_decision_memory_endpoint_uses_verified_tenant_and_subject(self):
        runtime = FakeRuntime()
        runtime.tenant_decision_memory = FakeRuntime.TenantDecisionMemory()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/memory/decisions", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "TENANT_SCOPED")
        context = runtime.tenant_decision_memory.contexts[0]
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.subject_id, "alice")
        self.assertFalse(body["execution_authorized"])

    def test_local_tenant_statistics_and_report_use_only_configured_owner_memory(self):
        runtime = FakeRuntime()
        runtime.tenant_decision_memory.records = [
            DecisionRecord(
                decision_id="local-1", created_at="2026-11-26T12:00:00+00:00",
                symbol="EURUSD", timeframe="M5", signal="COMPRA", score=82.0,
                confirmed=True, reason="contexto validado", outcome="WIN",
            )
        ]
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, stats = call_wsgi(app, "/api/analysis/statistics")
            report_status, report = call_wsgi(app, "/api/analysis/report?limit=10")
        self.assertEqual(status, "200 OK")
        self.assertEqual(stats["scope"], "TENANT_SCOPED")
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["win_rate"], 100.0)
        self.assertTrue(stats["win_rate_is_historical_outcome_ratio_not_prediction"])
        self.assertEqual(report_status, "200 OK")
        self.assertEqual(report["scope"], "TENANT_SCOPED")
        self.assertEqual(report["record_count"], 1)
        self.assertEqual(report["statistics_records_considered"], 1)
        self.assertEqual(report["records"][0]["decision_id"], "local-1")
        self.assertEqual(report["statistics_scope"], "ALL_LOADED_TENANT_DECISIONS")
        self.assertTrue(all(c.subject_id == "local-owner" for c in runtime.tenant_decision_memory.contexts))

    def test_local_analysis_run_uses_configured_owner_and_server_controlled_flags(self):
        runtime = FakeRuntime()

        class Analyzer:
            def __init__(self):
                self.calls = []

            def analyze(self, **kwargs):
                self.calls.append(kwargs)
                return {"signal": "AGUARDAR", "execution_authorized": False}

        runtime.market_analysis_service = Analyzer()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app, "/api/analysis/run", method="POST",
                body={"symbol": "EURUSD", "timeframe": "M5", "confirmed": True, "filters_ok": False},
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "TENANT_SCOPED")
        self.assertFalse(body["execution_authorized"])
        self.assertFalse(body["order_submitted"])
        call = runtime.market_analysis_service.calls[0]
        self.assertEqual(call["symbol"], "EURUSD")
        self.assertEqual(call["timeframe"], "M5")
        self.assertFalse(call["confirmed"])
        self.assertTrue(call["filters_ok"])
        self.assertEqual(call["decision_context"].tenant_id, "local-single-user")
        self.assertEqual(call["decision_context"].subject_id, "local-owner")

    def test_remote_analysis_run_passes_verified_tenant_context(self):
        runtime = FakeRuntime()

        class Analyzer:
            def __init__(self):
                self.calls = []

            def analyze(self, **kwargs):
                self.calls.append(kwargs)
                return {"signal": "COMPRA", "execution_authorized": False}

        runtime.market_analysis_service = Analyzer()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/analysis/run", method="POST",
                body={"symbol": "GBPUSD", "timeframe": "M10"},
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["analysis"]["signal"], "COMPRA")
        context = runtime.market_analysis_service.calls[0]["decision_context"]
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.subject_id, "alice")

    def test_analysis_run_rejects_invalid_timeframe_parameters_and_missing_provider(self):
        runtime = FakeRuntime()
        runtime.market_analysis_service = None
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            missing_status, missing_body = call_wsgi(
                app, "/api/analysis/run", method="POST",
                body={"symbol": "EURUSD", "timeframe": "M5"},
            )
            runtime.market_analysis_service = type(
                "Analyzer", (), {"analyze": lambda self, **kwargs: {"signal": "AGUARDAR"}}
            )()
            invalid_status, invalid_body = call_wsgi(
                app, "/api/analysis/run", method="POST",
                body={"symbol": "EURUSD", "timeframe": "M5", "limit": True},
            )
        self.assertEqual(missing_status, "503 Service Unavailable")
        self.assertEqual(missing_body["state"], "ANALYSIS_NOT_CONFIGURED")
        self.assertEqual(invalid_status, "400 Bad Request")
        self.assertFalse(invalid_body["execution_authorized"])

    def test_remote_tenant_statistics_are_scoped_to_verified_identity(self):
        runtime = FakeRuntime()
        runtime.tenant_decision_memory.records = [
            DecisionRecord(
                decision_id="tenant-record", created_at="2026-11-26T12:00:00+00:00",
                symbol="GBPUSD", timeframe="M15", signal="VENDA", score=75.0,
                confirmed=True, reason="contexto validado", outcome="LOSS",
            )
        ]
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/analysis/statistics", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "TENANT_SCOPED")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["losses"], 1)
        context = runtime.tenant_decision_memory.contexts[-1]
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.subject_id, "alice")

    def test_remote_tenant_analytics_rejects_unverified_identity(self):
        runtime = FakeRuntime()
        runtime.tenant_decision_memory.contexts.clear()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/analysis/statistics", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
            )
        # The outer access gate rejects unverified remote identity before
        # any tenant-scoped route can execute.
        self.assertEqual(status, "503 Service Unavailable")
        self.assertFalse(body["execution_authorized"])
        self.assertEqual(runtime.tenant_decision_memory.contexts, [])

    def test_tenant_report_rejects_invalid_limit(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(app, "/api/analysis/report?limit=1001")
        self.assertEqual(status, "400 Bad Request")
        self.assertFalse(body["execution_authorized"])

    def test_remote_market_monitor_uses_verified_tenant_and_subject_scope(self):
        runtime = FakeRuntime()
        runtime.market_monitor.calls.clear()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        requests = [
            ("/api/market-monitor/status", "GET", None, "200 OK"),
            ("/api/market-monitor/results", "GET", None, "200 OK"),
            ("/api/market-monitor/subscriptions", "GET", None, "200 OK"),
            ("/api/market-monitor/subscriptions", "POST", {"symbol": "EURUSD", "timeframe": "M5"}, "201 Created"),
            ("/api/market-monitor/subscriptions", "DELETE", {"symbol": "EURUSD", "timeframe": "M5"}, "200 OK"),
        ]
        with patch.dict("os.environ", settings):
            for path, method, body, expected_status in requests:
                status, response = call_wsgi(
                    app, path, method=method, body=body,
                    remote_addr="203.0.113.10",
                    authorization="Bearer shared-gateway-secret",
                    identity_verified=True, remote_user="alice", tenant_id="tenant-a",
                )
                self.assertEqual(status, expected_status, path)
                self.assertFalse(response["execution_authorized"])
            status, response = call_wsgi(
                app, "/api/intelligence/route", method="POST",
                body={"area": "Análise", "task": "analisar"},
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "503 Service Unavailable")
            self.assertEqual(response["state"], "TENANT_ISOLATION_NOT_IMPLEMENTED")
        self.assertEqual(
            runtime.market_monitor.calls,
            [
                ("status", "tenant-a", "alice"),
                ("results", "tenant-a", "alice"),
                ("subscriptions", "tenant-a", "alice"),
                ("subscribe", "tenant-a", "alice"),
                ("unsubscribe", "tenant-a", "alice"),
            ],
        )

    def test_remote_market_monitor_never_reuses_another_subject_context(self):
        runtime = FakeRuntime()
        runtime.market_monitor.calls.clear()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            for subject in ("alice", "bob"):
                status, _ = call_wsgi(
                    app, "/api/market-monitor/subscriptions",
                    remote_addr="203.0.113.10",
                    authorization="Bearer shared-gateway-secret",
                    identity_verified=True, remote_user=subject, tenant_id="tenant-a",
                )
                self.assertEqual(status, "200 OK")
        self.assertEqual(
            runtime.market_monitor.calls,
            [
                ("subscriptions", "tenant-a", "alice"),
                ("subscriptions", "tenant-a", "bob"),
            ],
        )


    def test_remote_notifications_are_isolated_by_verified_tenant_and_subject(self):
        runtime = FakeRuntime()
        runtime.tenant_state.save_notifications(
            type("Context", (), {"key": "tenant:tenant-a:subject:alice"})(),
            [{"notification_id": "alice-only"}],
        )
        runtime.tenant_state.save_notifications(
            type("Context", (), {"key": "tenant:tenant-a:subject:bob"})(),
            [{"notification_id": "bob-only"}],
        )
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, alice = call_wsgi(
                app, "/api/notifications", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "200 OK")
            status, bob = call_wsgi(
                app, "/api/notifications", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(alice["scope"], "TENANT_SCOPED")
        self.assertEqual([n["notification_id"] for n in alice["notifications"]], ["alice-only"])
        self.assertEqual([n["notification_id"] for n in bob["notifications"]], ["bob-only"])

    def test_remote_notifications_fail_closed_without_verified_identity(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/notifications", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertFalse(body["execution_authorized"])

    def test_remote_backup_status_hides_global_backup_details(self):
        runtime = FakeRuntime()
        class Scheduler:
            def status(self):
                return {
                    "enabled": True,
                    "worker_running": True,
                    "last_status": "SUCCESS",
                    "last_result": {"results": [{"path": "/private/backups/alice.sqlite3"}]},
                    "off_host_replication": "NOT_CONFIGURED",
                    "deployment_continuity": "PROCESS_LIFETIME_ONLY",
                    "execution_authorized": False,
                }
        runtime.backup_scheduler = Scheduler()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/backup/status",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertTrue(body["enabled"])
        self.assertTrue(body["worker_running"])
        self.assertEqual(body["scope"], "INFRASTRUCTURE_ONLY")
        self.assertNotIn("last_result", body)
        self.assertNotIn("last_status", body)
        self.assertNotIn("results", body)
        self.assertFalse(body["execution_authorized"])

    def test_remote_mt5_bridge_status_hides_global_source_and_candle_counts(self):
        runtime = FakeRuntime()
        class Relay:
            def status(self):
                return {
                    "connected": True, "account_mode": "DEMO",
                    "source_id": "private-workstation",
                    "stored_candles": 9876, "last_seen": "2026-11-27T00:00:00+00:00",
                    "read_only": True, "execution_authorized": False,
                }
        runtime.mt5_relay_store = Relay()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/bridge/mt5/status",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertTrue(body["configured"])
        self.assertEqual(body["scope"], "INFRASTRUCTURE_ONLY")
        self.assertNotIn("source_id", body)
        self.assertNotIn("stored_candles", body)
        self.assertNotIn("last_seen", body)
        self.assertFalse(body["execution_authorized"])

    def test_remote_readiness_exposes_only_infrastructure_contract(self):
        runtime = FakeRuntime()
        runtime.assistant.readiness = lambda: {"private_global_counter": 987}
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/readiness",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "INFRASTRUCTURE_ONLY")
        self.assertEqual(body["tenant_readiness"], "AVAILABLE_ONLY_THROUGH_SCOPED_ENDPOINTS")
        self.assertEqual(body["notifications"], "USE_TENANT_SCOPED_STATUS_ENDPOINT")
        self.assertEqual(
            body["deployment_topology"], "SINGLE_HOST_SQLITE_MULTI_REPLICA_BLOCKED"
        )
        self.assertNotIn("private_global_counter", body)
        self.assertNotIn("storage_foundation", body)
        self.assertNotIn("decision_memory", body)
        self.assertFalse(body["execution_authorized"])


    def test_remote_assistant_uses_only_tenant_fiscal_context(self):
        runtime = FakeRuntime()
        runtime.tenant_fiscal_store_factory = object()
        calls = []

        def ask_tenant(**kwargs):
            calls.append(kwargs)
            return {
                "conversation_id": "tenant-conversation",
                "answer": "Contexto fiscal individual",
                "scope": "TENANT_AND_SUBJECT",
                "context_scope": "TENANT_AND_SUBJECT",
                "read_only": True,
                "execution_allowed": False,
                "may_execute_orders": False,
                "may_enable_real": False,
                "may_move_money": False,
            }

        runtime.assistant.ask_tenant = ask_tenant
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/assistant/ask", method="POST",
                body={"message": "Resumo da minha Reserva Fiscal"},
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["scope"], "TENANT_AND_SUBJECT")
        self.assertTrue(body["read_only"])
        self.assertFalse(body["execution_authorized"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tenant_context"].tenant_id, "tenant-a")
        self.assertEqual(calls[0]["tenant_context"].subject_id, "alice")
        self.assertIs(calls[0]["fiscal_store_factory"], runtime.tenant_fiscal_store_factory)
        self.assertNotIn("fiscal_owner_id", calls[0])

    def test_remote_assistant_fails_closed_without_tenant_fiscal_factory(self):
        runtime = FakeRuntime()
        runtime.tenant_fiscal_store_factory = None
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/assistant/ask", method="POST",
                body={"message": "Resumo"},
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(body["state"], "FISCAL_TENANT_ISOLATION_REQUIRED")
        self.assertFalse(body["execution_authorized"])

    def test_notification_status_reports_no_external_sink_honestly(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/notifications/status")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["external_delivery"], "OUTBOX_ONLY_NO_PROVIDER")
        self.assertFalse(body["delivery_worker"]["configured"])

    def test_local_notification_status_reports_tenant_outbox_separately(self):
        from integration.tenant_notification_dispatcher import TenantNotificationDispatcher
        from security.sqlite_tenant_storage import SQLiteTenantStorage
        from security.tenant_context import TenantContext
        from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState
        from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity

        runtime = FakeRuntime()
        runtime.local_tenant_context = TenantContext("local-single-user", "local-user")
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(SQLiteTenantStorage(Path(directory) / "tenant-state.sqlite3"))
            runtime.tenant_notification_dispatcher = TenantNotificationDispatcher(state)
            runtime.tenant_notification_dispatcher.publish(
                runtime.local_tenant_context,
                EcosystemNotification(
                    notification_id="local-tenant-event", kind=NotificationKind.MARKET,
                    severity=NotificationSeverity.INFO, title="EURUSD", message="Novo sinal",
                ),
            )
            app = StandaloneWSGIApplication(runtime)
            status, body = call_wsgi(app, "/api/notifications/status")
            self.assertEqual(status, "200 OK")
            self.assertEqual(body["tenant_outbox"]["PENDING"], 1)
            self.assertEqual(body["tenant_external_delivery"], "OUTBOX_ONLY_NO_PROVIDER")
            self.assertFalse(body["tenant_delivery_worker"]["configured"])

    def test_notification_status_distinguishes_configured_but_stopped_worker(self):
        runtime = FakeRuntime()

        class StoppedWorker:
            def status(self):
                return {
                    "configured": True,
                    "running": False,
                    "state": "STOPPED",
                    "last_error": None,
                    "last_result": None,
                    "outbox": {"PENDING": 1, "IN_FLIGHT": 0, "DELIVERED": 0, "DEAD": 0},
                }

        runtime.notification_worker = StoppedWorker()
        app = StandaloneWSGIApplication(runtime)
        status, body = call_wsgi(app, "/api/notifications/status")

        self.assertEqual(status, "200 OK")
        self.assertEqual(body["external_delivery"], "WORKER_STOPPED")
        self.assertTrue(body["delivery_worker"]["configured"])
        self.assertFalse(body["delivery_worker"]["running"])
        self.assertEqual(body["delivery_worker"]["outbox"]["PENDING"], 1)

    def test_notification_status_surfaces_degraded_worker(self):
        runtime = FakeRuntime()

        class DegradedWorker:
            def status(self):
                return {
                    "configured": True,
                    "running": True,
                    "state": "DEGRADED",
                    "last_error": "provider timeout",
                    "last_result": None,
                    "outbox": {"PENDING": 1, "IN_FLIGHT": 0, "DELIVERED": 0, "DEAD": 0},
                }

        runtime.notification_worker = DegradedWorker()
        app = StandaloneWSGIApplication(runtime)
        status, body = call_wsgi(app, "/api/notifications/status")

        self.assertEqual(status, "200 OK")
        self.assertEqual(body["external_delivery"], "WORKER_DEGRADED")
        self.assertTrue(body["delivery_worker"]["running"])
        self.assertEqual(body["delivery_worker"]["state"], "DEGRADED")

    def test_notification_status_reports_running_worker(self):
        runtime = FakeRuntime()

        class RunningWorker:
            def status(self):
                return {
                    "configured": True,
                    "running": True,
                    "state": "RUNNING",
                    "last_error": None,
                    "last_result": {"claimed": 1, "delivered": 1, "retried": 0, "dead_lettered": 0},
                    "last_cycle_at": 123.0,
                    "outbox": {"PENDING": 0, "IN_FLIGHT": 0, "DELIVERED": 1, "DEAD": 0},
                }

        runtime.notification_worker = RunningWorker()
        app = StandaloneWSGIApplication(runtime)
        status, body = call_wsgi(app, "/api/notifications/status")

        self.assertEqual(status, "200 OK")
        self.assertEqual(body["external_delivery"], "WORKER_RUNNING")
        self.assertTrue(body["delivery_worker"]["running"])
        self.assertEqual(body["delivery_worker"]["last_result"]["delivered"], 1)

    def test_remote_notification_status_counts_only_verified_subject_notifications(self):
        runtime = FakeRuntime()
        runtime.tenant_state.save_notifications(
            type("Context", (), {"key": "tenant:tenant-a:subject:alice"})(),
            [{"notification_id": "alice-only"}],
        )
        runtime.tenant_state.save_notifications(
            type("Context", (), {"key": "tenant:tenant-a:subject:bob"})(),
            [{"notification_id": "bob-only"}, {"notification_id": "bob-second"}],
        )
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, alice = call_wsgi(
                app, "/api/notifications/status", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "200 OK")
            status, bob = call_wsgi(
                app, "/api/notifications/status", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(alice["scope"], "TENANT_SCOPED")
        self.assertEqual(alice["total"], 1)
        self.assertEqual(bob["scope"], "TENANT_SCOPED")
        self.assertEqual(bob["total"], 2)
        self.assertFalse(alice["execution_authorized"])

    def test_notifications_endpoint_rejects_invalid_limit(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/notifications?limit=999")
        self.assertEqual(status, "400 Bad Request")
        self.assertFalse(body["execution_authorized"])

    def test_cors_allows_only_explicitly_configured_frontend_origin(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        with patch.dict("os.environ", {"CONTROLADOR_ALLOWED_ORIGINS": "https://app.example.com"}):
            status, body, headers = call_wsgi(
                app, "/api/health", origin="https://app.example.com",
                include_headers=True,
            )
            self.assertEqual(status, "200 OK")
            self.assertIn(
                ("Access-Control-Allow-Origin", "https://app.example.com"),
                headers,
            )
            denied_status, denied_body = call_wsgi(
                app, "/api/health", origin="https://attacker.example"
            )
            self.assertEqual(denied_status, "403 Forbidden")
            self.assertFalse(denied_body["execution_authorized"])

    def test_cors_preflight_supports_frontend_api_methods(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        with patch.dict("os.environ", {"CONTROLADOR_ALLOWED_ORIGINS": "https://app.example.com"}):
            status, _ = call_wsgi(
                app, "/api/market-monitor/subscriptions",
                method="OPTIONS", origin="https://app.example.com",
            )
        self.assertEqual(status, "204 No Content")


    def test_shared_bearer_token_alone_does_not_authenticate_remote_user(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/health", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn("identidade remota verificada", body["error"])
        self.assertFalse(body["execution_authorized"])

    def test_remote_access_requires_verified_subject_and_tenant(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/health", remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="user-123", tenant_id="tenant-abc",
            )
        self.assertEqual(status, "200 OK")
        self.assertFalse(body["execution_authorized"])

    def test_remote_access_is_denied_by_default(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        status, body = call_wsgi(app, "/api/health", remote_addr="203.0.113.10")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertFalse(body["execution_authorized"])



    def test_local_user_preferences_are_persisted_in_single_user_scope(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        settings = {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}
        with patch.dict("os.environ", settings):
            status, saved = call_wsgi(
                app, "/api/user/preferences", method="PUT",
                body={"preferences": {"language": "pt-BR", "compact_mode": True}},
            )
            self.assertEqual(status, "200 OK")
            self.assertEqual(saved["scope"], "TENANT_SCOPED")
            status, loaded = call_wsgi(app, "/api/user/preferences")
        self.assertEqual(status, "200 OK")
        self.assertEqual(
            loaded["preferences"],
            {"language": "pt-BR", "compact_mode": True},
        )
        self.assertFalse(loaded["execution_authorized"])

    def test_remote_user_preferences_are_isolated_by_verified_tenant_and_subject(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, _ = call_wsgi(
                app, "/api/user/preferences", method="PUT",
                body={"preferences": {"language": "pt-BR"}},
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "200 OK")
            status, bob = call_wsgi(
                app, "/api/user/preferences",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(bob["preferences"], {})

    def test_local_user_preferences_fail_closed_without_configured_identity(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": ""}):
            status, body = call_wsgi(
                app, "/api/user/preferences", method="PUT",
                body={"preferences": {"language": "pt-BR"}},
            )
        self.assertEqual(status, "403 Forbidden")
        self.assertFalse(body["execution_authorized"])

    def test_user_preferences_reject_non_object_payload(self):
        app = StandaloneWSGIApplication(FakeRuntime())
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app, "/api/user/preferences", method="PUT",
                body={"preferences": ["not", "an", "object"]},
            )
        self.assertEqual(status, "400 Bad Request")
        self.assertFalse(body["execution_authorized"])


    def test_per_account_analysis_uses_only_the_requested_tenant_adapter(self):
        class Session:
            connection_id = "a" * 32
            provider_id = "broker_x"
            source = "broker_x:account-a"
            adapter = object()

        class Sessions:
            def get(self, context, *, connection_id):
                assert context.tenant_id == "tenant-a"
                assert context.subject_id == "alice"
                assert connection_id == "a" * 32
                return Session()

        class DecisionMemory:
            def save(self, context, record):
                return True

        runtime = FakeRuntime()
        runtime.tenant_market_data_sessions = Sessions()
        runtime.intelligence = object()
        runtime.tenant_decision_memory = DecisionMemory()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings), patch(
            "integration.standalone_market_analysis.StandaloneMarketAnalysisService"
        ) as analyzer_class:
            analyzer_class.return_value.analyze.return_value = {
                "signal": "AGUARDAR", "execution_authorized": False
            }
            status, body = call_wsgi(
                app, f"/api/market-data/connections/{'a' * 32}/analysis",
                method="POST", body={"symbol": "EURUSD", "timeframe": "M5"},
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["connection"]["provider_id"], "broker_x")
        self.assertEqual(body["connection"]["source"], "broker_x:account-a")
        self.assertFalse(body["execution_authorized"])
        analyzer_class.return_value.analyze.assert_called_once()

    def test_per_account_analysis_returns_not_found_for_unbound_or_other_tenant_account(self):
        class Sessions:
            def get(self, context, *, connection_id):
                assert context.tenant_id == "tenant-b"
                return None

        runtime = FakeRuntime()
        runtime.tenant_market_data_sessions = Sessions()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, f"/api/market-data/connections/{'a' * 32}/analysis",
                method="POST", body={"symbol": "EURUSD", "timeframe": "M5"},
                remote_addr="203.0.113.11",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-b",
            )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(body["state"], "ADAPTER_NOT_BOUND")
        self.assertFalse(body["execution_authorized"])


    def test_account_timeframe_subscription_routes_are_tenant_scoped(self):
        class Monitor:
            def subscribe(self, context, connection_id, symbol, timeframe):
                assert context.tenant_id == "tenant-a"
                assert context.subject_id == "alice"
                assert connection_id == "a" * 32
                return {"symbol": symbol, "timeframe": timeframe, "enabled": True}

            def subscriptions(self, context, connection_id):
                assert context.tenant_id == "tenant-a"
                return [{"connection_id": connection_id, "symbol": "EURUSD", "timeframe": "M5"}]

            def unsubscribe(self, context, connection_id, symbol, timeframe):
                assert context.tenant_id == "tenant-a"
                return True

        runtime = FakeRuntime()
        runtime.tenant_market_monitor = Monitor()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        path = f"/api/market-data/connections/{'a' * 32}/subscriptions"
        with patch.dict("os.environ", settings):
            status, created = call_wsgi(
                app, path, method="POST", body={"symbol": "EURUSD", "timeframe": "M5"},
                remote_addr="203.0.113.12", authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "201 Created")
            self.assertTrue(created["enabled"])
            status, listed = call_wsgi(
                app, path, method="GET", remote_addr="203.0.113.12",
                authorization="Bearer shared-gateway-secret", identity_verified=True,
                remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "200 OK")
            self.assertEqual(listed["subscriptions"][0]["timeframe"], "M5")
            status, removed = call_wsgi(
                app, path, method="DELETE",
                body={"symbol": "EURUSD", "timeframe": "M5"},
                remote_addr="203.0.113.12", authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "200 OK")
            self.assertTrue(removed["unsubscribed"])

    def test_account_timeframe_subscriptions_fail_closed_without_trusted_identity(self):
        class Monitor:
            def subscribe(self, *args, **kwargs):
                raise AssertionError("must not reach monitor without identity")

        runtime = FakeRuntime()
        runtime.tenant_market_monitor = Monitor()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, f"/api/market-data/connections/{'a' * 32}/subscriptions",
                method="POST", body={"symbol": "EURUSD", "timeframe": "M5"},
                remote_addr="203.0.113.13", authorization="Bearer shared-gateway-secret",
            )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertFalse(body["execution_authorized"])


    def test_provider_connection_inventory_is_tenant_scoped_and_reports_runtime_binding(self):
        class SessionRegistry:
            def __init__(self):
                self.contexts = []

            def status(self, context):
                self.contexts.append(context)
                return [{
                    "connection_id": "a" * 32,
                    "provider_id": "broker_a",
                    "account_alias": "Conta A",
                    "status": "CONNECTED",
                    "adapter_status": "NOT_BOUND",
                    "health_status": "NOT_BOUND",
                    "health": {},
                    "read_only": True,
                    "execution_authorized": False,
                }]

        runtime = FakeRuntime()
        registry = SessionRegistry()
        runtime.tenant_market_data_sessions = registry
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/market-data/connections", method="GET",
                remote_addr="203.0.113.24",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["connections"][0]["adapter_status"], "NOT_BOUND")
        self.assertEqual(body["connections"][0]["health_status"], "NOT_BOUND")
        self.assertEqual(registry.contexts[0].tenant_id, "tenant-a")
        self.assertEqual(registry.contexts[0].subject_id, "alice")
        self.assertFalse(body["execution_authorized"])

    def test_provider_connect_api_accepts_only_tenant_owned_credential_reference(self):
        class ConnectionService:
            def __init__(self):
                self.calls = []

            def connect(self, context, **kwargs):
                self.calls.append((context, kwargs))
                return {
                    "connection_id": "a" * 32,
                    "provider_id": kwargs["provider_id"],
                    "status": "CONNECTED",
                    "execution_authorized": False,
                }

        runtime = FakeRuntime()
        service = ConnectionService()
        runtime.tenant_provider_connection_service = service
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        headers = {
            "remote_addr": "203.0.113.21",
            "authorization": "Bearer shared-gateway-secret",
            "identity_verified": True,
            "remote_user": "alice",
            "tenant_id": "tenant-a",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/market-data/connections", method="POST",
                body={
                    "provider_id": "broker_a",
                    "account_alias": "Conta A",
                    "credential_ref": "vault://tenant-a/broker-a",
                },
                **headers,
            )
        self.assertEqual(status, "201 Created")
        self.assertEqual(service.calls[0][0].tenant_id, "tenant-a")
        self.assertEqual(
            service.calls[0][1]["credential_ref"], "vault://tenant-a/broker-a"
        )
        self.assertFalse(body["execution_authorized"])

    def test_provider_reconnect_api_requires_trusted_owner_and_revalidates_saved_account(self):
        class ConnectionService:
            def __init__(self):
                self.calls = []

            def reconnect_saved(self, context, *, connection_id):
                self.calls.append((context, connection_id))
                return {
                    "connection_id": connection_id,
                    "provider_id": "broker_a",
                    "status": "CONNECTED",
                    "adapter_status": "ADAPTER_BOUND",
                    "read_only": True,
                    "execution_authorized": False,
                }

        runtime = FakeRuntime()
        service = ConnectionService()
        runtime.tenant_provider_connection_service = service
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, f"/api/market-data/connections/{'a' * 32}/reconnect",
                method="POST",
                remote_addr="203.0.113.22",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["status"], "CONNECTED")
        self.assertEqual(body["adapter_status"], "ADAPTER_BOUND")
        self.assertEqual(service.calls[0][0].tenant_id, "tenant-a")
        self.assertEqual(service.calls[0][0].subject_id, "alice")
        self.assertEqual(service.calls[0][1], "a" * 32)
        self.assertFalse(body["execution_authorized"])

    def test_provider_reconnect_api_rejects_invalid_connection_id(self):
        class ConnectionService:
            def reconnect_saved(self, *args, **kwargs):
                raise AssertionError("invalid connection IDs must be rejected first")

        runtime = FakeRuntime()
        runtime.tenant_provider_connection_service = ConnectionService()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/market-data/connections/not-an-id/reconnect",
                method="POST",
                remote_addr="203.0.113.23",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "400 Bad Request")
        self.assertFalse(body["execution_authorized"])

    def test_provider_connect_api_rejects_raw_credentials_in_request_body(self):
        class ConnectionService:
            def connect(self, *args, **kwargs):
                raise AssertionError("raw credentials must be rejected before service call")

        runtime = FakeRuntime()
        runtime.tenant_provider_connection_service = ConnectionService()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/market-data/connections", method="POST",
                body={
                    "provider_id": "broker_a", "account_alias": "Conta A",
                    "credential_ref": "vault://tenant-a/broker-a",
                    "api_key": "must-not-enter-the-application",
                },
                remote_addr="203.0.113.22",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "400 Bad Request")
        self.assertFalse(body["execution_authorized"])

    def test_provider_disconnect_api_revokes_only_authenticated_account_binding(self):
        class ConnectionService:
            def disconnect(self, context, *, connection_id):
                assert context.tenant_id == "tenant-a"
                assert connection_id == "a" * 32
                return {"disconnected": True, "status": "DISCONNECTED", "execution_authorized": False}

        class CTraderTokenVault:
            def __init__(self): self.revoked = []
            def revoke(self, context, connection_id):
                self.revoked.append((context.tenant_id, context.subject_id, connection_id))
                return True

        runtime = FakeRuntime()
        runtime.tenant_provider_connection_service = ConnectionService()
        runtime.tenant_ctrader_token_vault = CTraderTokenVault()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, f"/api/market-data/connections/{'a' * 32}", method="DELETE",
                remote_addr="203.0.113.23",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertTrue(body["disconnected"])
        self.assertFalse(body["execution_authorized"])
        self.assertEqual(runtime.tenant_ctrader_token_vault.revoked, [
            ("tenant-a", "alice", "a" * 32)
        ])

if __name__ == "__main__":
    unittest.main()


class PublicBindSecurityTests(unittest.TestCase):
    def test_loopback_bind_remains_available_without_remote_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            _validate_bind_security("127.0.0.1")
            _validate_bind_security("::1")
            _validate_bind_security("localhost")

    def test_public_bind_is_blocked_without_complete_remote_identity_boundary(self):
        with patch.dict("os.environ", {}, clear=True):
            for host in ("0.0.0.0", "::", "192.0.2.10"):
                with self.subTest(host=host):
                    with self.assertRaisesRegex(RuntimeError, "bind público bloqueado"):
                        _validate_bind_security(host)

    def test_public_bind_requires_remote_access_token_and_trusted_middleware(self):
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "true",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "configured-test-token",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "true",
        }
        with patch.dict("os.environ", settings, clear=True):
            _validate_bind_security("0.0.0.0")

        for missing in settings:
            incomplete = dict(settings)
            incomplete.pop(missing)
            with patch.dict("os.environ", incomplete, clear=True):
                with self.assertRaisesRegex(RuntimeError, "bind público bloqueado"):
                    _validate_bind_security("0.0.0.0")

    def test_ctrader_oauth_callback_requires_https_and_uses_one_time_state_service(self):
        class OAuth:
            def __init__(self):
                self.calls = []

            def complete_callback(self, *, state, code):
                self.calls.append((state, code))
                return {
                    "status": "OAUTH_TOKEN_STORED_PENDING_DEMO_HANDSHAKE",
                    "account_connected": False,
                    "execution_authorized": False,
                }

        runtime = FakeRuntime()
        runtime.tenant_ctrader_oauth_service = OAuth()
        app = StandaloneWSGIApplication(runtime)
        status, body = call_wsgi(
            app, "/api/oauth/ctrader/callback?state=opaque-state&code=one-time-code",
            scheme="http",
        )
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(runtime.tenant_ctrader_oauth_service.calls, [])
        status, body = call_wsgi(
            app, "/api/oauth/ctrader/callback?state=opaque-state&code=one-time-code",
            scheme="https",
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(runtime.tenant_ctrader_oauth_service.calls, [("opaque-state", "one-time-code")])
        self.assertFalse(body["account_connected"])
        self.assertFalse(body["execution_authorized"])

    def test_ctrader_oauth_start_is_scoped_to_local_identity(self):
        class OAuth:
            def __init__(self):
                self.calls = []

            def begin(self, context, *, connection_id):
                self.calls.append((context.tenant_id, context.subject_id, connection_id))
                return {
                    "authorization_url": "https://id.ctrader.com/consent?state=opaque",
                    "state_reveal": "ONE_TIME",
                    "execution_authorized": False,
                }

        runtime = FakeRuntime()
        runtime.tenant_ctrader_oauth_service = OAuth()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app, "/api/market-data/connections/" + "a" * 32 + "/ctrader-oauth",
                method="POST",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(runtime.tenant_ctrader_oauth_service.calls, [
            ("local-single-user", "local-owner", "a" * 32)
        ])
        self.assertFalse(body["execution_authorized"])



    def test_ctrader_oauth_provision_creates_pending_connection_from_alias_only(self):
        class OAuth:
            def __init__(self):
                self.calls = []
            def provision(self, context, *, account_alias):
                self.calls.append((context.tenant_id, context.subject_id, account_alias))
                return {
                    "connection_id": "c" * 32,
                    "provider_id": "ctrader_open_api",
                    "status": "PENDING_OAUTH",
                    "authorization_url": "https://id.ctrader.com/consent?state=one-time",
                    "account_connected": False,
                    "execution_authorized": False,
                }

        runtime = FakeRuntime()
        runtime.tenant_ctrader_oauth_service = OAuth()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app,
                "/api/market-data/ctrader-oauth-connections",
                method="POST",
                body={"account_alias": "Demo principal"},
            )
        self.assertEqual(status, "201 Created")
        self.assertEqual(runtime.tenant_ctrader_oauth_service.calls, [
            ("local-single-user", "local-owner", "Demo principal")
        ])
        self.assertEqual(body["status"], "PENDING_OAUTH")
        self.assertFalse(body["account_connected"])
        self.assertFalse(body["execution_authorized"])

    def test_ctrader_oauth_provision_rejects_extra_credentials_in_request(self):
        class OAuth:
            def provision(self, context, *, account_alias):
                raise AssertionError("provision must not be called")
        runtime = FakeRuntime()
        runtime.tenant_ctrader_oauth_service = OAuth()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app,
                "/api/market-data/ctrader-oauth-connections",
                method="POST",
                body={"account_alias": "Demo", "access_token": "should-not-be-accepted"},
            )
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("somente account_alias", body["error"])


    def test_ctrader_demo_account_listing_is_tenant_scoped(self):
        class AccountService:
            def __init__(self): self.calls = []
            def list_demo_accounts(self, context, *, connection_id):
                self.calls.append((context.tenant_id, context.subject_id, connection_id))
                return {
                    "connection_id": connection_id,
                    "accounts": [{"account_id": 123, "account_mode": "DEMO"}],
                    "real_accounts_exposed": False,
                    "execution_authorized": False,
                }
        runtime = FakeRuntime()
        runtime.tenant_ctrader_account_service = AccountService()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app, "/api/market-data/connections/" + "a" * 32 + "/ctrader-accounts"
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["accounts"], [{"account_id": 123, "account_mode": "DEMO"}])
        self.assertFalse(body["real_accounts_exposed"])
        self.assertEqual(runtime.tenant_ctrader_account_service.calls, [
            ("local-single-user", "local-owner", "a" * 32)
        ])

    def test_ctrader_account_selection_accepts_only_account_id(self):
        class AccountService:
            def __init__(self): self.calls = []
            def connect_demo(self, context, *, connection_id, account_id):
                self.calls.append((context.tenant_id, context.subject_id, connection_id, account_id))
                return {
                    "connection_id": connection_id,
                    "status": "CONNECTED",
                    "account_mode": "DEMO",
                    "execution_authorized": False,
                }
        runtime = FakeRuntime()
        runtime.tenant_ctrader_account_service = AccountService()
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, body = call_wsgi(
                app, "/api/market-data/connections/" + "b" * 32 + "/ctrader-account",
                method="POST", body={"account_id": 123},
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["account_mode"], "DEMO")
        self.assertFalse(body["execution_authorized"])
        self.assertEqual(runtime.tenant_ctrader_account_service.calls, [
            ("local-single-user", "local-owner", "b" * 32, 123)
        ])


    def test_remote_provider_status_exposes_only_requesting_owners_oauth_refresh_health(self):
        class Connections:
            def list_connections(self, context):
                assert context.tenant_id == "tenant-a"
                assert context.subject_id == "alice"
                return []

        class RefreshWorkers:
            def owner_status(self, context):
                assert context.tenant_id == "tenant-a"
                assert context.subject_id == "alice"
                return {
                    "configured": True, "registered": True, "running": True,
                    "state": "RUNNING", "execution_authorized": False,
                }

            def status(self):
                raise AssertionError("global worker counts must never be exposed remotely")

        runtime = FakeRuntime()
        runtime.tenant_provider_connections = Connections()
        runtime.tenant_oauth_refresh_worker = RefreshWorkers()
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, body = call_wsgi(
                app, "/api/market-data/providers",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
        self.assertEqual(status, "200 OK")
        self.assertEqual(body["oauth_token_refresh"]["state"], "RUNNING")
        self.assertNotIn("registered_owner_count", body["oauth_token_refresh"])
        self.assertFalse(body["oauth_token_refresh"]["execution_authorized"])



class PushSubscriptionStandaloneRouteTests(unittest.TestCase):
    class Store:
        production_durable = True
        encrypted_at_rest = True

        def __init__(self):
            self.rows = {}

        def list_for_owner(self, context):
            return [
                {**value, "device_id": device}
                for (tenant, subject, device), value in self.rows.items()
                if tenant == context.tenant_id and subject == context.subject_id
            ]

        def put_for_owner(self, context, device_id, record):
            self.rows[(context.tenant_id, context.subject_id, device_id)] = record

        def delete_for_owner(self, context, device_id):
            return self.rows.pop((context.tenant_id, context.subject_id, device_id), None) is not None

    @staticmethod
    def subscription_payload():
        public_key = b"\x04" + b"p" * 64
        return {
            "device_id": "browser-1",
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/example",
                "keys": {
                    "p256dh": base64.urlsafe_b64encode(public_key).decode().rstrip("="),
                    "auth": base64.urlsafe_b64encode(b"a" * 16).decode().rstrip("="),
                },
                "expirationTime": None,
            },
        }

    def test_push_subscription_routes_mount_only_when_registry_is_injected(self):
        runtime = FakeRuntime()
        runtime.tenant_push_subscription_registry = TenantPushSubscriptionRegistry(self.Store())
        app = StandaloneWSGIApplication(runtime)
        with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
            status, created = call_wsgi(
                app, "/api/push/subscriptions", method="POST",
                body=self.subscription_payload(),
            )
            self.assertEqual(status, "201 Created")
            self.assertEqual(created["device"]["status"], "ACTIVE")

            status, listed = call_wsgi(app, "/api/push/subscriptions")
            self.assertEqual(status, "200 OK")
            self.assertEqual(listed["devices"][0]["device_id"], "browser-1")
            self.assertNotIn("endpoint", listed["devices"][0])

            status, revoked = call_wsgi(
                app, "/api/push/subscriptions/browser-1", method="DELETE",
            )
            self.assertEqual(status, "200 OK")
            self.assertTrue(revoked["device"]["revoked"])

    def test_push_routes_use_verified_remote_tenant_and_deny_missing_identity(self):
        runtime = FakeRuntime()
        runtime.tenant_push_subscription_registry = TenantPushSubscriptionRegistry(self.Store())
        app = StandaloneWSGIApplication(runtime)
        settings = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
            "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
            "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
        }
        with patch.dict("os.environ", settings):
            status, denied = call_wsgi(
                app, "/api/push/subscriptions",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
            )
            self.assertEqual(status, "503 Service Unavailable")

            status, created = call_wsgi(
                app, "/api/push/subscriptions", method="POST",
                body=self.subscription_payload(),
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="alice", tenant_id="tenant-a",
            )
            self.assertEqual(status, "201 Created")

            status, bob = call_wsgi(
                app, "/api/push/subscriptions",
                remote_addr="203.0.113.10",
                authorization="Bearer shared-gateway-secret",
                identity_verified=True, remote_user="bob", tenant_id="tenant-a",
            )
            self.assertEqual(status, "200 OK")
            self.assertEqual(bob["devices"], [])


    def test_remote_notification_status_never_reads_unscoped_tenant_worker_counts(self):
        from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
        from integration.tenant_notification_dispatcher import TenantNotificationDispatcher
        from security.sqlite_tenant_storage import SQLiteTenantStorage
        from security.tenant_context import TenantContext
        from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState

        runtime = FakeRuntime()
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(
                SQLiteTenantStorage(Path(directory) / "tenant-notification-status.sqlite3")
            )
            dispatcher = TenantNotificationDispatcher(state)
            alice = TenantContext("tenant-a", "alice")
            bob = TenantContext("tenant-a", "bob")
            for owner, notification_id in ((alice, "alice-event"), (bob, "bob-event")):
                dispatcher.publish(
                    owner,
                    EcosystemNotification(
                        notification_id=notification_id,
                        kind=NotificationKind.MARKET,
                        severity=NotificationSeverity.INFO,
                        title="Sinal",
                        message="Atualização",
                    ),
                )

            class ContextRequiredWorker:
                def status(self, context):
                    assert isinstance(context, TenantContext)
                    return {
                        "configured": True,
                        "running": True,
                        "state": "RUNNING",
                        "outbox": dispatcher.outbox.status_counts(context),
                    }

            runtime.tenant_state = state
            runtime.tenant_notification_dispatcher = dispatcher
            runtime.tenant_notification_worker = ContextRequiredWorker()
            app = StandaloneWSGIApplication(runtime)
            settings = {
                "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "1",
                "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "shared-gateway-secret",
                "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "1",
            }
            with patch.dict("os.environ", settings):
                status, alice_body = call_wsgi(
                    app, "/api/notifications/status", remote_addr="203.0.113.10",
                    authorization="Bearer shared-gateway-secret",
                    identity_verified=True, remote_user="alice", tenant_id="tenant-a",
                )
                status, bob_body = call_wsgi(
                    app, "/api/notifications/status", remote_addr="203.0.113.10",
                    authorization="Bearer shared-gateway-secret",
                    identity_verified=True, remote_user="bob", tenant_id="tenant-a",
                )

        assert status == "200 OK"
        assert alice_body["tenant_outbox"]["PENDING"] == 1
        assert bob_body["tenant_outbox"]["PENDING"] == 1
        assert alice_body["tenant_delivery_worker"]["outbox"]["PENDING"] == 1
        assert bob_body["tenant_delivery_worker"]["outbox"]["PENDING"] == 1
        assert alice_body["scope"] == "TENANT_SCOPED"
        assert bob_body["scope"] == "TENANT_SCOPED"



def test_local_readiness_exposes_calendar_worker_and_news_evidence_status():
    class FakeCalendarWorker:
        def status(self):
            return {
                "configured": True,
                "worker_running": True,
                "source_count": 2,
                "execution_authorized": False,
            }

    class FakeCorrelator:
        store = object()

    runtime = FakeRuntime()
    runtime.economic_calendar_worker = FakeCalendarWorker()
    runtime.ecosystem_service.news_evidence_correlator = FakeCorrelator()
    app = StandaloneWSGIApplication(runtime)

    with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
        status, body = call_wsgi(app, "/api/readiness")

    assert status == "200 OK"
    assert body["economic_calendar_ingestion"]["worker_running"] is True
    assert body["news_evidence"]["status"] == "CONFIGURED"
    assert body["news_evidence"]["persistent_store"] == "CONFIGURED"


def test_remote_readiness_does_not_expose_shared_calendar_or_news_evidence_state():
    runtime = FakeRuntime()
    runtime.economic_calendar_worker = object()
    runtime.ecosystem_service.news_evidence_correlator = object()
    app = StandaloneWSGIApplication(runtime)

    with patch.dict("os.environ", {
        "CONTROLADOR_REMOTE_ACCESS_REQUIRED": "true",
        "CONTROLADOR_STANDALONE_ACCESS_TOKEN": "test-token",
        "CONTROLADOR_TRUSTED_IDENTITY_MIDDLEWARE": "true",
    }):
        status, body = call_wsgi(
            app,
            "/api/readiness",
            remote_addr="203.0.113.10",
            authorization="Bearer test-token",
            identity_verified=True,
            remote_user="alice",
            tenant_id="tenant-a",
        )

    assert status == "200 OK"
    assert "economic_calendar_ingestion" not in body
    assert "news_evidence" not in body



def test_local_readiness_exposes_news_polling_worker_but_remote_does_not():
    class FakeNewsWorker:
        def status(self):
            return {
                "configured": True,
                "worker_running": True,
                "last_state": "POLL_SUCCEEDED",
                "execution_authorized": False,
            }

    runtime = FakeRuntime()
    runtime.news_polling_worker = FakeNewsWorker()
    app = StandaloneWSGIApplication(runtime)
    with patch.dict("os.environ", {"CONTROLADOR_SINGLE_USER_IDENTITY": "local-owner"}):
        status, body = call_wsgi(app, "/api/readiness")
    assert status == "200 OK"
    assert body["news_polling"]["worker_running"] is True
    assert body["news_polling"]["last_state"] == "POLL_SUCCEEDED"



def test_runtime_factory_uses_default_when_no_host_factory_is_configured():
    expected = object.__new__(StandaloneRuntime)
    expected.closed = False
    with patch.dict("os.environ", {"CONTROLADOR_STANDALONE_RUNTIME_FACTORY": ""}):
        with patch.object(StandaloneRuntime, "from_environment", return_value=expected):
            assert _runtime_from_environment() is expected


def test_runtime_factory_loads_trusted_operator_module():
    expected = object.__new__(StandaloneRuntime)
    expected.closed = False
    module = types.SimpleNamespace(build_runtime=lambda: expected)
    with patch.dict("os.environ", {
        "CONTROLADOR_STANDALONE_RUNTIME_FACTORY": "deployment.runtime:build_runtime",
    }):
        with patch("standalone_app.importlib.import_module", return_value=module) as importer:
            assert _runtime_from_environment() is expected
    importer.assert_called_once_with("deployment.runtime")


def test_runtime_factory_rejects_invalid_spec_without_fallback():
    with patch.dict("os.environ", {
        "CONTROLADOR_STANDALONE_RUNTIME_FACTORY": "../deployment:build_runtime",
    }):
        with patch.object(StandaloneRuntime, "from_environment") as fallback:
            try:
                _runtime_from_environment()
            except RuntimeError as exc:
                assert "formato modulo:funcao" in str(exc)
            else:
                raise AssertionError("invalid factory spec must fail startup")
    fallback.assert_not_called()


def test_runtime_factory_rejects_non_runtime_result():
    module = types.SimpleNamespace(build_runtime=lambda: object())
    with patch.dict("os.environ", {
        "CONTROLADOR_STANDALONE_RUNTIME_FACTORY": "deployment.runtime:build_runtime",
    }):
        with patch("standalone_app.importlib.import_module", return_value=module):
            try:
                _runtime_from_environment()
            except RuntimeError as exc:
                assert "StandaloneRuntime ativo" in str(exc)
            else:
                raise AssertionError("factory returning the wrong type must fail startup")
