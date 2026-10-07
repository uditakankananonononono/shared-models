"""Real loopback HTTP tests; all credentials and prompts are synthetic."""
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from instinct_models.providers import http_json, _jev_http, ProviderError, JevStatusError


class TransportRedirectTests(unittest.TestCase):
    def setUp(self):
        self.seen = []
        seen = self.seen

        class Sink(BaseHTTPRequestHandler):
            def respond(self):
                size = int(self.headers.get('Content-Length', 0))
                seen.append((self.command, self.headers.get('Authorization'), self.rfile.read(size)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            do_GET = respond
            do_POST = respond
            def log_message(self, *args):
                pass

        self.sink = ThreadingHTTPServer(('127.0.0.1', 0), Sink)
        sink_port = self.sink.server_port

        class Source(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                code = int(self.path.strip('/'))
                self.send_response(code)
                self.send_header('Location', f'http://localhost:{sink_port}/sink')
                self.end_headers()
            def log_message(self, *args):
                pass

        self.source = ThreadingHTTPServer(('127.0.0.1', 0), Source)
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True)
                        for s in (self.sink, self.source)]
        for t in self.threads:
            t.start()

    def tearDown(self):
        for s in (self.source, self.sink):
            s.shutdown()
            s.server_close()
        for t in self.threads:
            t.join(timeout=2)

    def test_post_redirects_never_contact_sink(self):
        for transport in (http_json, _jev_http):
            for code in (301, 302, 303, 307, 308):
                with self.subTest(transport=transport.__name__, code=code):
                    self.seen.clear()
                    with self.assertRaises(ProviderError) as caught:
                        transport(f'http://127.0.0.1:{self.source.server_port}/{code}',
                                  {'private': 'synthetic prompt'},
                                  {'Authorization': 'Bearer test-only-token'}, 2)
                    self.assertEqual(self.seen, [])
                    if transport is _jev_http:
                        self.assertIsInstance(caught.exception, JevStatusError)
                        self.assertEqual(caught.exception.status, code)

    def test_direct_posts_still_send_body_and_authorization(self):
        for transport in (http_json, _jev_http):
            with self.subTest(transport=transport.__name__):
                self.seen.clear()
                out = transport(f'http://127.0.0.1:{self.sink.server_port}/direct',
                                {'private': 'synthetic prompt'},
                                {'Authorization': 'Bearer test-only-token'}, 2)
                self.assertTrue(out['ok'])
                self.assertEqual(len(self.seen), 1)
                method, auth, body = self.seen[0]
                self.assertEqual(method, 'POST')
                self.assertEqual(auth, 'Bearer test-only-token')
                self.assertIn(b'synthetic prompt', body)
