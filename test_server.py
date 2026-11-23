import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import segno

from server import (
    ProjectHandler,
    GithubApiError,
    build_spayd_payload,
    github_request,
    list_github_pages,
    make_qr_svg,
    normalize_account,
)


class PaymentQrTests(unittest.TestCase):
    def test_github_api_error_preserves_safe_status_and_message(self):
        error = HTTPError(
            "https://api.github.com/test",
            403,
            "Forbidden",
            hdrs=None,
            fp=BytesIO(b'{"message":"Resource not accessible"}'),
        )
        with patch("server.urlopen", side_effect=error):
            with self.assertRaises(GithubApiError) as raised:
                github_request("PUT", "/test", "secret-token", {})
        error.close()

        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(str(raised.exception), "Resource not accessible")

    def test_github_page_links_include_project_pages_prefix(self):
        with patch.dict(
            "server.os.environ",
            {"PUBLIC_SITE_URL": "https://248837-del.github.io/Akce"},
        ), patch(
            "server.github_request",
            return_value=[{"type": "file", "name": "test-akce.html"}],
        ):
            pages = list_github_pages("248837-del/Akce", "token")

        self.assertEqual(
            pages,
            [{
                "title": "test-akce",
                "path": "https://248837-del.github.io/Akce/Akce/test-akce.html",
            }],
        )

    def test_normalizes_czech_account_to_iban(self):
        self.assertEqual(
            normalize_account("19-2000145399/0800"),
            "CZ6508000000192000145399",
        )

    def test_accepts_valid_iban(self):
        self.assertEqual(
            normalize_account("CZ65 0800 0000 1920 0014 5399"),
            "CZ6508000000192000145399",
        )

    def test_rejects_invalid_account_and_amount(self):
        with self.assertRaises(ValueError):
            normalize_account("123/1")
        with self.assertRaises(ValueError):
            build_spayd_payload("123456789/0100", 0, "Akce - Fíla")

    def test_builds_qr_platba_payload_and_svg(self):
        payload = build_spayd_payload(
            "123456789/0100",
            2097,
            "Akce - Fíla",
        )
        self.assertIn("*AM:20.97*CC:CZK*MSG:Akce%20-%20F%C3%ADla", payload)
        self.assertFalse(segno.make(payload, error="M", micro=False).is_micro)
        self.assertIn(b"<svg", make_qr_svg(payload))

    def test_qr_api_returns_svg(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ProjectHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/qr",
                data=json.dumps({
                    "account": "123456789/0100",
                    "amount_halere": 2097,
                    "reference": "Akce - Fíla",
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("image/svg+xml", response.headers["Content-Type"])
                self.assertIn(b"<svg", response.read())
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_create_page_saves_account_for_qr_payments(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            pages_directory = Path(temporary_directory)
            server = ThreadingHTTPServer(("127.0.0.1", 0), ProjectHandler)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                data = {
                    "title": "Test akce",
                    "date": "",
                    "account": "123456789/0100",
                    "payer": "Test",
                    "participants": ["Test"],
                    "shoppingList": {
                        "currency": "CZK",
                        "items": [{
                            "product": "Test",
                            "quantity": 1,
                            "line_total_czk": 10,
                        }],
                    },
                }
                invalid_data = dict(data, payer="Neznámý")
                invalid_request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/pages",
                    data=json.dumps(invalid_data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with patch("server.PAGES_DIR", pages_directory):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(invalid_request)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()

                missing_account_request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/pages",
                    data=json.dumps(dict(data, account="")).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with patch("server.PAGES_DIR", pages_directory):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(missing_account_request)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()

                request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/pages",
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with patch("server.PAGES_DIR", pages_directory):
                    with urlopen(request) as response:
                        result = json.loads(response.read())

                page = (pages_directory / "test-akce.html").read_text(encoding="utf-8")
                self.assertEqual(response.status, 201)
                self.assertIn('data-account="CZ1801000000000123456789"', page)
                self.assertIn('data-payer="Test"', page)
                self.assertEqual(result["path"], "/Akce/test-akce.html")
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

if __name__ == "__main__":
    unittest.main()
