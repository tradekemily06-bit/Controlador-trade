from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from security.secure_transport import (
    TransportSecurityStatus,
    is_trusted_proxy,
    production_transport_status,
    require_production_request_transport,
    require_secure_transport,
)


class SecureTransportBoundaryTests(unittest.TestCase):
    def test_missing_status_fails_closed(self):
        with self.assertRaises(RuntimeError):
            require_secure_transport(None)

    def test_incomplete_transport_fails_closed(self):
        with self.assertRaises(RuntimeError):
            require_secure_transport(TransportSecurityStatus(tls_enabled=True))
        with self.assertRaises(RuntimeError):
            require_secure_transport(TransportSecurityStatus(trusted_proxy_configured=True))

    def test_complete_transport_is_ready(self):
        status = TransportSecurityStatus(tls_enabled=True, trusted_proxy_configured=True)
        self.assertTrue(status.ready_for_production)
        self.assertIs(require_secure_transport(status), status)

    def test_forwarded_https_is_ignored_from_untrusted_proxy(self):
        environ = {
            "REMOTE_ADDR": "10.0.0.9",
            "wsgi.url_scheme": "http",
            "HTTP_X_FORWARDED_PROTO": "https",
        }
        with patch.dict(os.environ, {"CONTROLADOR_TRUSTED_PROXY_CIDRS": "192.0.2.0/24"}, clear=False):
            status = production_transport_status(environ)
        self.assertFalse(status.tls_enabled)
        self.assertTrue(status.trusted_proxy_configured)
        self.assertFalse(is_trusted_proxy("10.0.0.9"))

    def test_forwarded_https_is_accepted_only_from_trusted_proxy(self):
        environ = {
            "REMOTE_ADDR": "192.0.2.10",
            "wsgi.url_scheme": "http",
            "HTTP_X_FORWARDED_PROTO": "https",
        }
        with patch.dict(os.environ, {"CONTROLADOR_TRUSTED_PROXY_CIDRS": "192.0.2.0/24"}, clear=False):
            status = require_production_request_transport(environ)
        self.assertTrue(status.tls_enabled)
        self.assertTrue(status.trusted_proxy_configured)

    def test_direct_https_requires_explicit_proxy_configuration_for_production(self):
        environ = {"REMOTE_ADDR": "192.0.2.10", "wsgi.url_scheme": "https"}
        with patch.dict(os.environ, {"CONTROLADOR_TRUSTED_PROXY_CIDRS": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                require_production_request_transport(environ)


if __name__ == "__main__":
    unittest.main()
