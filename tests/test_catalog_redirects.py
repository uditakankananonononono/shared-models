"""Catalog requests must remain at the robots-checked URL."""
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from instinct_models.catalog import _get


class CatalogRedirectTests(unittest.TestCase):
    def test_redirect_never_contacts_unchecked_target(self):
        seen = []

        class Server(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/direct':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'<a href="/tools/test">Test</a>')
                elif self.path == '/sink':
                    seen.append(self.path)
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_response(int(self.path.strip('/')))
                    self.send_header('Location', f'http://localhost:{self.server.server_port}/sink')
                    self.end_headers()
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            self.assertIn('Test', _get(base + '/direct', timeout=2))
            for code in (301, 302, 303, 307, 308):
                with self.subTest(code=code):
                    seen.clear()
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        _get(base + f'/{code}', timeout=2)
                    self.assertEqual(caught.exception.code, code)
                    self.assertEqual(seen, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
