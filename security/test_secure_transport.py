from __future__ import annotations

import unittest

from security.secure_transport import TransportSecurityStatus, require_secure_transport


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


if __name__ == "__main__":
    unittest.main()
