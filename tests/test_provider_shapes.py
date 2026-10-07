"""Malformed inference responses fail as provider errors so routing can continue."""
import unittest
from instinct_models import OrnithOpenAICompat, Router, Task


class ProviderShapeTests(unittest.TestCase):
    def test_malformed_responses_do_not_crash_or_report_success(self):
        malformed = [None, [], {}, {'choices': []},
                     {'choices': [{'message': None}]},
                     {'choices': [{'message': {'content': 42}}]},
                     {'choices': [{'message': {'tool_calls': 'bad'}}]},
                     {'choices': [{'message': {'tool_calls': [None]}}]},
                     {'choices': [{'message': {'tool_calls': [{'function': {}}]}}]},
                     {'choices': [{'message': {'tool_calls': [{'function': {'name': 'x', 'arguments': 'broken'}}]}}]},
                     {'choices': [{'message': {'tool_calls': [{'function': {'name': 'x', 'arguments': '[]'}}]}}]},
                     {'choices': [{'message': {'tool_calls': [{'function': {'name': '', 'arguments': '{}'}}]}}]}]
        for data in malformed:
            with self.subTest(data=data):
                provider = OrnithOpenAICompat('http://localhost:1234/v1', 'test', transport=lambda *a: data)
                out = Router([provider]).run(Task([{'role': 'user', 'content': 'synthetic'}]))
                self.assertFalse(out.ok)
                self.assertEqual(out.attempts[0].outcome, 'error')

    def test_malformed_route_can_escalate_to_valid_route(self):
        bad = OrnithOpenAICompat('http://localhost:1234/v1', 'bad', transport=lambda *a: {'choices': [{'message': None}]})
        good = OrnithOpenAICompat('http://localhost:1234/v1', 'good', transport=lambda *a: {'choices': [{'message': {'content': 'answer'}}]})
        out = Router([bad, good]).run(Task([{'role': 'user', 'content': 'synthetic'}]))
        self.assertTrue(out.ok)
        self.assertEqual(out.result.text, 'answer')
        self.assertEqual([a.outcome for a in out.attempts], ['error', 'ok'])

    def test_deeply_nested_arguments_escalate_instead_of_crashing(self):
        data = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'x', 'arguments': '[' * 1100 + '0' + ']' * 1100}}]}}]}
        bad = OrnithOpenAICompat('http://localhost:1234/v1', 'bad', transport=lambda *a: data)
        good = OrnithOpenAICompat('http://localhost:1234/v1', 'good', transport=lambda *a: {'choices': [{'message': {'content': 'answer'}}]})
        out = Router([bad, good]).run(Task([{'role': 'user', 'content': 'synthetic'}]))
        self.assertEqual(out.result.text, 'answer')
        self.assertEqual([a.outcome for a in out.attempts], ['error', 'ok'])

    def test_real_http_invalid_json_escalates_instead_of_crashing(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class InvalidJSON(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'not-json')
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), InvalidJSON)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            bad = OrnithOpenAICompat(f'http://127.0.0.1:{server.server_port}/v1', 'bad')
            good = OrnithOpenAICompat('http://localhost:1234/v1', 'good', transport=lambda *a: {'choices': [{'message': {'content': 'answer'}}]})
            out = Router([bad, good]).run(Task([{'role': 'user', 'content': 'synthetic'}]))
            self.assertEqual(out.result.text, 'answer')
            self.assertEqual([a.outcome for a in out.attempts], ['error', 'ok'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
