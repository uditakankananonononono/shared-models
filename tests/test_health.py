"""Shape validation and origin checks for zero-token health reads."""
import unittest
from unittest.mock import patch
from instinct_models.health import probe, hf_token_valid


class HealthTests(unittest.TestCase):
    def test_valid_json_wrong_shapes_are_unavailable_not_exceptions(self):
        for data in (None, [], 3, 'ok', {}, {'data': None}, {'data': {}},
                     {'data': ['model']}, {'data': [{}]}, {'data': [{'id': 3}]}):
            with self.subTest(data=data), patch('instinct_models.health._get', return_value=data):
                self.assertFalse(probe('http://localhost:1234/v1', 'm')['ok'])

    def test_model_inventory_is_not_inference(self):
        with patch('instinct_models.health._get', return_value={'data': [{'id': 'm'}]}):
            out = probe('http://localhost:1234/v1', 'm')
            self.assertTrue(out['ok'])
            self.assertTrue(out['model_listed'])
            self.assertFalse(probe('http://localhost:1234/v1', 'missing')['model_listed'])

    def test_only_exact_hf_router_origin_invokes_token_check(self):
        with patch('instinct_models.health._get', return_value={'data': []}), \
                patch('instinct_models.health.hf_token_valid', return_value=False) as check:
            for url in ('https://huggingface.co.attacker.invalid/v1',
                        'https://attacker.invalid/huggingface.co/v1',
                        'https://router.huggingface.co.attacker.invalid/v1'):
                self.assertTrue(probe(url, 'm')['ok'])
            check.assert_not_called()
            self.assertFalse(probe('https://router.huggingface.co/v1', 'm')['ok'])
            check.assert_called_once()

    def test_whoami_wrong_shape_does_not_authenticate(self):
        for data in (None, [], {'name': True}, {'name': ''}, {'name': 12}):
            with self.subTest(data=data), patch('instinct_models.health._get', return_value=data):
                self.assertIs(hf_token_valid('test-only-token'), False)


class RedirectSecurityTests(unittest.TestCase):
    def test_real_http_redirect_never_reaches_other_host_with_token(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen = []

        class Sink(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data": []}')

            def log_message(self, *args):
                pass

        sink = ThreadingHTTPServer(('127.0.0.1', 0), Sink)

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(int(self.path.split('/')[1]))
                self.send_header('Location', f'http://localhost:{sink.server_port}/sink')
                self.end_headers()

            def log_message(self, *args):
                pass

        source = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (sink, source)]
        for t in threads:
            t.start()
        try:
            for code in (301, 302, 303, 307, 308):
                with self.subTest(code=code):
                    out = probe(f'http://127.0.0.1:{source.server_port}/{code}', 'm',
                                'test-only-token', timeout=2)
                    self.assertEqual(seen, [], 'redirect contacted credential sink')
                    self.assertFalse(out['ok'])
                    self.assertEqual(out['error'], f'HTTP {code}')
        finally:
            for s in (source, sink):
                s.shutdown()
                s.server_close()
            for t in threads:
                t.join(timeout=2)

    def test_real_http_direct_request_still_authenticates(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen = []

        class Direct(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data": [{"id": "m"}]}')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Direct)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            out = probe(f'http://127.0.0.1:{server.server_port}/v1', 'm', 'test-only-token', timeout=2)
            self.assertTrue(out['ok'])
            self.assertTrue(out['model_listed'])
            self.assertEqual(seen, ['Bearer test-only-token'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
