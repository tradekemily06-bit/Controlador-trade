import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from app import application
from security_guard import MAX_BODY_BYTES


class AppSecurityTests(unittest.TestCase):
    def setUp(self):
        import app
        from finance.fiscal_reserve import FiscalReserve
        from finance.fiscal_pending_queue import FiscalPendingQueue
        self.app_module = app
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_fiscal_db = app.FISCAL_RESERVE_DB
        self.old_reserve = app.FISCAL_RESERVE
        self.old_queue = app.FISCAL_PENDING_QUEUE
        self.old_identity = os.environ.get("CONTROLADOR_SINGLE_USER_IDENTITY")
        os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "test-security-owner"
        path = Path(self.temp_dir.name) / "fiscal.sqlite3"
        app.FISCAL_RESERVE_DB = path
        app.FISCAL_RESERVE = FiscalReserve(str(path))
        app.FISCAL_PENDING_QUEUE = FiscalPendingQueue(str(path))

    def tearDown(self):
        self.app_module.FISCAL_RESERVE_DB = self.old_fiscal_db
        self.app_module.FISCAL_RESERVE = self.old_reserve
        self.app_module.FISCAL_PENDING_QUEUE = self.old_queue
        if self.old_identity is None:
            os.environ.pop("CONTROLADOR_SINGLE_USER_IDENTITY", None)
        else:
            os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = self.old_identity
        self.temp_dir.cleanup()

    def request(self, path, method="GET", payload=None, remote="test-client", headers=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        parsed_path = urlsplit(path)
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": parsed_path.path,
            "QUERY_STRING": parsed_path.query,
            "CONTENT_TYPE": "application/json" if payload is not None else "",
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_ADDR": remote,
            "wsgi.input": io.BytesIO(body),
        }
        for key, value in (headers or {}).items():
            environ[key] = value
        response = b"".join(application(environ, start_response))
        return captured["status"], captured["headers"], response

    def test_security_headers_and_request_id_are_returned(self):
        status, headers, _ = self.request("/api/health")
        self.assertEqual(status, "200 OK")
        self.assertTrue(headers["X-Request-ID"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_oversized_json_is_rejected(self):
        payload = {"value": "x" * (MAX_BODY_BYTES + 1)}
        status, _, body = self.request("/api/analyze", method="POST", payload=payload)
        self.assertEqual(status, "400 Bad Request")
        self.assertIn(b"Entrada inv\xc3\xa1lida", body)


    def test_local_health_probe_is_not_throttled(self):
        from app import SECURITY
        old_limit = SECURITY.limit
        try:
            SECURITY.limit = 1
            for _ in range(5):
                status, _, _ = self.request("/api/health", remote="127.0.0.1")
                self.assertEqual(status, "200 OK")
        finally:
            SECURITY.limit = old_limit
            SECURITY._buckets.clear()

    def test_rate_limit_is_per_client(self):
        from app import SECURITY
        old_limit = SECURITY.limit
        try:
            SECURITY.limit = 1
            first, _, _ = self.request("/api/health", remote="client-a")
            blocked, _, _ = self.request("/api/health", remote="client-a")
            other, _, _ = self.request("/api/health", remote="client-b")
            self.assertEqual(first, "200 OK")
            self.assertEqual(blocked, "429 Too Many Requests")
            self.assertEqual(other, "200 OK")
        finally:
            SECURITY.limit = old_limit
            SECURITY._buckets.clear()

    def test_local_mutation_is_denied_when_explicitly_disabled(self):
        from app import _authorize_remote_mutation
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "false"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            os.environ["CONTROLADOR_LOCAL_MUTATION_HOSTS"] = "localhost,127.0.0.1"
            allowed, reason = _authorize_remote_mutation(
                {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": "localhost:8000"}
            )
            self.assertFalse(allowed)
            self.assertEqual(reason, "local mutations are disabled")
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


    def test_explicit_local_notebook_mutation_requires_local_host(self):
        from app import _authorize_remote_mutation
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "false"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "true"
            os.environ["CONTROLADOR_LOCAL_MUTATION_HOSTS"] = "localhost,127.0.0.1"
            local_allowed, _ = _authorize_remote_mutation(
                {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": "localhost:8000"}
            )
            public_host_denied, _ = _authorize_remote_mutation(
                {"REMOTE_ADDR": "127.0.0.1", "HTTP_HOST": "controlador.example.com"}
            )
            remote_denied, _ = _authorize_remote_mutation(
                {"REMOTE_ADDR": "10.0.0.25", "HTTP_HOST": "controlador.example.com"}
            )
            self.assertTrue(local_allowed)
            self.assertFalse(public_host_denied)
            self.assertFalse(remote_denied)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_remote_access_requires_trusted_identity_when_enabled(self):
        from app import _authorize_remote_mutation
        names = {"CONTROLADOR_REMOTE_ACCESS_REQUIRED", "CONTROLADOR_TRUSTED_IDENTITY_HEADER", "CONTROLADOR_SINGLE_USER_IDENTITY", "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"}
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "user@example.com"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            allowed, _ = _authorize_remote_mutation({"REMOTE_ADDR": "203.0.113.10", "HTTP_X_AUTHENTICATED_USER": "user@example.com"})
            denied, _ = _authorize_remote_mutation({"REMOTE_ADDR": "203.0.113.10"})
            self.assertTrue(allowed)
            self.assertFalse(denied)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


    def test_assistant_conversation_reads_require_trusted_identity_remotely(self):
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
            "CONTROLADOR_SINGLE_USER_IDENTITY",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "audit-user@example.com"
            denied, _, denied_body = self.request(
                "/api/assistant/conversations", remote="203.0.113.20"
            )
            allowed, _, allowed_body = self.request(
                "/api/assistant/conversations",
                remote="203.0.113.20",
                headers={"HTTP_X_AUTHENTICATED_USER": "audit-user@example.com"},
            )
            self.assertEqual(denied, "401 Unauthorized")
            self.assertIn("Identidade autenticada necessária".encode(), denied_body)
            self.assertEqual(allowed, "200 OK")
            self.assertIn(b'"conversations"', allowed_body)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


    def test_all_remote_assistant_routes_require_trusted_identity(self):
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
            "CONTROLADOR_SINGLE_USER_IDENTITY",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "audit-user@example.com"
            routes = [
                ("/api/assistant/conversations", "GET", None),
                ("/api/assistant/history?conversation_id=not-owned", "GET", None),
                ("/api/assistant/chat", "POST", {"message": "teste"}),
            ]
            for path, method, payload in routes:
                status, _, body = self.request(path, method=method, payload=payload, remote="203.0.113.44")
                self.assertEqual(status, "401 Unauthorized", path)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


    def test_fiscal_rate_api_never_exposes_legacy_foreign_percentage(self):
        old_required = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED")
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "false"
            status, _, body = self.request(
                "/api/fiscal-reserve/rates",
                method="POST",
                payload={"rates": {"BR_DAY_TRADE": 20}},
                remote="127.0.0.1",
            )
            self.assertEqual(status, "200 OK")
            response = json.loads(body)
            self.assertEqual(response["settings"], {"BR_DAY_TRADE": 20.0})
            self.assertNotIn("FOREIGN_FINANCIAL_ASSET", response["settings"])
            self.assertNotIn("15.0", body.decode("utf-8"))
        finally:
            if old_required is None:
                os.environ.pop("CONTROLADOR_REMOTE_ACCESS_REQUIRED", None)
            else:
                os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = old_required

    def test_remote_fiscal_and_assistant_delete_routes_require_identity(self):
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
            "CONTROLADOR_LOCAL_MUTATION_HOSTS",
            "CONTROLADOR_SINGLE_USER_IDENTITY",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "audit-user@example.com"
            routes = [
                ("/api/fiscal-reserve", "GET", None),
                ("/api/fiscal-reserve/mt5-preview", "GET", None),
                ("/api/fiscal-reserve/pending", "GET", None),
                ("/api/fiscal-reserve/pending/00000000-0000-0000-0000-000000000000/reviews", "GET", None),
                ("/api/fiscal-reserve/pending/00000000-0000-0000-0000-000000000000/reviews", "POST", {"candidate_classification": "ETF", "confirmed_jurisdiction": "US", "reviewer_name": "Teste", "reviewer_role": "contador", "professional_registration": "CRC-TESTE", "evidence_reference": "DOC-1", "reviewed_on": "2026-11-03"}),
                ("/api/fiscal-reserve/pending", "POST", {"reference": "REMOTE-UNAUTH", "original_amount": 1, "original_currency": "USD", "instrument": "ETF", "jurisdiction": "US", "occurred_on": "2026-11-02"}),
                ("/api/fiscal-reserve/rates", "POST", {"category": "BR_DAY_TRADE", "rate": 20}),
                ("/api/fiscal-reserve/results", "POST", {"category": "BR_DAY_TRADE", "realized_result_brl": 10, "reference": "REMOTE-UNAUTH"}),
                ("/api/assistant/conversations", "DELETE", None),
            ]
            expected = [
                "403 Forbidden", "403 Forbidden", "403 Forbidden", "403 Forbidden", "401 Unauthorized",
                "401 Unauthorized", "401 Unauthorized", "401 Unauthorized",
                "401 Unauthorized",
            ]
            for (path, method, payload), expected_status in zip(routes, expected):
                status, _, _ = self.request(
                    path, method=method, payload=payload, remote="203.0.113.77"
                )
                self.assertEqual(status, expected_status, f"{method} {path}")
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


    def test_remote_access_fails_closed_when_single_user_identity_is_unset(self):
        from app import _authorize_remote_mutation
        names = {"CONTROLADOR_REMOTE_ACCESS_REQUIRED", "CONTROLADOR_TRUSTED_IDENTITY_HEADER", "CONTROLADOR_SINGLE_USER_IDENTITY", "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"}
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ.pop("CONTROLADOR_SINGLE_USER_IDENTITY", None)
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            allowed, reason = _authorize_remote_mutation({"REMOTE_ADDR": "203.0.113.9", "HTTP_X_AUTHENTICATED_USER": "someone@example.com"})
            self.assertFalse(allowed)
            self.assertEqual(reason, "single-user identity is not configured")
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_single_user_identity_pin_blocks_other_access_identity_for_fiscal_and_assistant(self):
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_SINGLE_USER_IDENTITY",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "owner@example.com"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            other_headers = {"HTTP_X_AUTHENTICATED_USER": "other@example.com"}
            fiscal, _, _ = self.request("/api/fiscal-reserve", remote="203.0.113.88", headers=other_headers)
            assistant, _, _ = self.request("/api/assistant/conversations", remote="203.0.113.88", headers=other_headers)
            self.assertEqual(fiscal, "403 Forbidden")
            self.assertEqual(assistant, "403 Forbidden")
            owner_headers = {"HTTP_X_AUTHENTICATED_USER": "OWNER@example.com"}
            fiscal_owner, _, _ = self.request("/api/fiscal-reserve", remote="203.0.113.88", headers=owner_headers)
            assistant_owner, _, _ = self.request("/api/assistant/conversations", remote="203.0.113.88", headers=owner_headers)
            self.assertEqual(fiscal_owner, "200 OK")
            self.assertEqual(assistant_owner, "200 OK")
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_fiscal_review_api_records_evidence_without_classifying_or_calculating(self):
        import tempfile
        from pathlib import Path
        import app as app_module
        from finance.fiscal_pending_queue import FiscalPendingQueue
        from finance.fiscal_schema import migrate_fiscal_schema

        old_queue = app_module.FISCAL_PENDING_QUEUE
        old_db = app_module.FISCAL_RESERVE_DB
        old_required = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED")
        old_identity = os.environ.get("CONTROLADOR_SINGLE_USER_IDENTITY")
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "false"
                os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "review-test-owner"
                fiscal_path = Path(directory) / "fiscal.sqlite"
                app_module.FISCAL_RESERVE_DB = fiscal_path
                queue = FiscalPendingQueue(str(fiscal_path))
                owner_id = migrate_fiscal_schema(str(fiscal_path))
                pending = queue.add(owner_id, {
                    "reference": "REVIEW-API-TEST",
                    "original_amount": 125.50,
                    "original_currency": "USD",
                    "instrument": "ETF",
                    "jurisdiction": "US",
                    "occurred_on": "2026-11-02",
                })
                app_module.FISCAL_PENDING_QUEUE = queue
                review_payload = {
                    "candidate_classification": "ETF",
                    "confirmed_jurisdiction": "US",
                    "reviewer_name": "Revisor de teste",
                    "reviewer_role": "contador",
                    "professional_registration": "CRC-TESTE",
                    "evidence_reference": "DOC-TESTE-1",
                    "reviewed_on": "2026-11-03",
                    "review_notes": "Registro de validação automatizada",
                }
                created, _, created_body = self.request(
                    f"/api/fiscal-reserve/pending/{pending['pending_id']}/reviews",
                    method="POST",
                    payload=review_payload,
                    remote="127.0.0.1",
                )
                self.assertEqual(created, "201 Created")
                created_data = json.loads(created_body)
                self.assertFalse(created_data["reserve_calculated"])
                self.assertEqual(
                    created_data["review"]["status_unchanged"],
                    "PENDING_CLASSIFICATION",
                )
                listed, _, listed_body = self.request(
                    f"/api/fiscal-reserve/pending/{pending['pending_id']}/reviews",
                    remote="127.0.0.1",
                )
                self.assertEqual(listed, "200 OK")
                listed_data = json.loads(listed_body)
                self.assertEqual(len(listed_data["reviews"]), 1)
                self.assertEqual(
                    listed_data["status_unchanged"],
                    "PENDING_CLASSIFICATION",
                )
                self.assertFalse(listed_data["reserve_calculated"])
            finally:
                app_module.FISCAL_PENDING_QUEUE = old_queue
                app_module.FISCAL_RESERVE_DB = old_db
                if old_identity is None:
                    os.environ.pop("CONTROLADOR_SINGLE_USER_IDENTITY", None)
                else:
                    os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = old_identity
                if old_required is None:
                    os.environ.pop("CONTROLADOR_REMOTE_ACCESS_REQUIRED", None)
                else:
                    os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = old_required



    def test_missing_remote_address_is_not_treated_as_local(self):
        from app import _authorize_remote_mutation
        old_required = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED")
        old_local = os.environ.get("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED")
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "false"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "false"
            for environ in ({}, {"REMOTE_ADDR": ""}):
                allowed, reason = _authorize_remote_mutation(environ)
                self.assertFalse(allowed)
                self.assertEqual(reason, "trusted remote identity provider is not configured")
        finally:
            if old_required is None:
                os.environ.pop("CONTROLADOR_REMOTE_ACCESS_REQUIRED", None)
            else:
                os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = old_required
            if old_local is None:
                os.environ.pop("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", None)
            else:
                os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = old_local


    def test_remote_access_cannot_use_local_mutation_bypass(self):
        from app import _authorize_remote_mutation
        names = {
            "CONTROLADOR_REMOTE_ACCESS_REQUIRED",
            "CONTROLADOR_TRUSTED_IDENTITY_HEADER",
            "CONTROLADOR_SINGLE_USER_IDENTITY",
            "CONTROLADOR_LOCAL_MUTATIONS_ALLOWED",
        }
        old = {name: os.environ.get(name) for name in names}
        try:
            os.environ["CONTROLADOR_REMOTE_ACCESS_REQUIRED"] = "true"
            os.environ["CONTROLADOR_TRUSTED_IDENTITY_HEADER"] = "X-Authenticated-User"
            os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "owner@example.com"
            os.environ["CONTROLADOR_LOCAL_MUTATIONS_ALLOWED"] = "true"
            local_without_identity, _ = _authorize_remote_mutation({
                "REMOTE_ADDR": "127.0.0.1",
                "HTTP_HOST": "localhost:8501",
            })
            local_with_identity, _ = _authorize_remote_mutation({
                "REMOTE_ADDR": "127.0.0.1",
                "HTTP_HOST": "localhost:8501",
                "HTTP_X_AUTHENTICATED_USER": "owner@example.com",
            })
            self.assertFalse(local_without_identity)
            self.assertTrue(local_with_identity)
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

if __name__ == "__main__":
    unittest.main()