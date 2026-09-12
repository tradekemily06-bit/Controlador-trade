import io
import unittest

from app import application


class CSPWebTests(unittest.TestCase):
    def test_html_get_uses_per_response_nonce_for_inline_script(self):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/",
            "QUERY_STRING": "",
            "REMOTE_ADDR": "127.0.0.1",
            "wsgi.input": io.BytesIO(b""),
        }
        body = b"".join(application(environ, start_response)).decode("utf-8")
        self.assertEqual(captured["status"], "200 OK")
        csp = captured["headers"]["Content-Security-Policy"]
        marker = "'nonce-"
        self.assertIn(marker, csp)
        nonce = csp.split(marker, 1)[1].split("'", 1)[0]
        self.assertTrue(nonce)
        self.assertIn(f'<script nonce="{nonce}">', body)
        self.assertNotIn("<script>", body)


if __name__ == "__main__":
    unittest.main()
