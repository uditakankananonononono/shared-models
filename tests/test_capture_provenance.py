"""Logic tests for scripts/capture_provenance.py using a fake loopback server and temp files.
These do NOT exercise any real model server; the script itself is UNRUN against one."""
import hashlib
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

spec = importlib.util.spec_from_file_location("cp", os.path.join(os.path.dirname(__file__), "..", "scripts", "capture_provenance.py"))
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            b = json.dumps({"data": [{"id": "fake-model"}]}).encode()
            self.send_response(200)
        else:
            b = b"nope"
            self.send_response(404)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class Capture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def weights(self, data=b"fake weights"):
        f = tempfile.NamedTemporaryFile(delete=False, suffix=".gguf")
        f.write(data)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name, hashlib.sha256(data).hexdigest()

    def test_reachability_and_hash_match_without_pid_leaves_binding_unverified(self):
        p, d = self.weights()
        r = cp.capture(self.url, "fake-model", [p], {os.path.basename(p): d})
        self.assertTrue(r["reachability"]["served_name_listed"])
        self.assertTrue(r["weights"]["files"][0]["matches_expected"])
        self.assertEqual(r["binding"]["verdict"], "unverified")
        self.assertTrue(r["all_requested_checks_passed"])  # no binding check was requested

    def test_hash_mismatch_and_wrong_served_name_fail(self):
        p, d = self.weights()
        r = cp.capture(self.url, "other-model", [p], {os.path.basename(p): "0" * 64})
        self.assertFalse(r["checks"]["served_name_listed"])
        self.assertFalse(r["weights"]["files"][0]["matches_expected"])
        self.assertFalse(r["all_requested_checks_passed"])

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "Linux /proc needed")
    def test_binding_confirmed_only_when_pid_holds_the_hashed_file(self):
        p, d = self.weights()
        with open(p, "rb"):
            r = cp.capture(self.url, "fake-model", [p], pid=os.getpid())
            self.assertEqual(r["binding"]["verdict"], "confirmed")
        r = cp.capture(self.url, "fake-model", [p], pid=os.getpid())  # file closed now
        self.assertEqual(r["binding"]["verdict"], "unverified")
        self.assertFalse(r["all_requested_checks_passed"])
        r = cp.capture(self.url, "fake-model", [p], pid=2 ** 22 + 12345)  # no such process
        self.assertEqual(r["binding"]["verdict"], "unverified")
        self.assertIsNotNone(r["binding"]["process_error"])

    def test_non_loopback_and_odd_urls_are_refused(self):
        for u in ("http://example.com:80/v1", "https://127.0.0.1:8080/v1", "http://127.0.0.1/v1", "http://10.0.0.5:8080/v1", "ftp://127.0.0.1:1"):
            with self.assertRaises(ValueError, msg=u):
                cp.capture(u, None, [])
        self.assertEqual(cp.main(["--base-url", "http://example.com:80/v1"]), 2)

    def test_dead_endpoint_and_missing_file_are_reported_not_raised(self):
        r = cp.capture("http://127.0.0.1:1/v1", "m", ["/nonexistent/file.gguf"])
        self.assertFalse(r["checks"]["reachable"])
        self.assertIn("error", r["weights"]["files"][0])
        self.assertFalse(r["all_requested_checks_passed"])

    def test_cli_exit_codes_and_report_file(self):
        p, d = self.weights()
        out = p + ".json"
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        self.assertEqual(cp.main(["--base-url", self.url, "--served-name", "fake-model", "--weights", p,
                                  "--expect-sha256", f"{os.path.basename(p)}={d}", "--out", out]), 0)
        self.assertEqual(json.load(open(out))["weights"]["files"][0]["sha256"], d)
        self.assertEqual(cp.main(["--base-url", self.url, "--served-name", "nope", "--out", out]), 1)


if __name__ == "__main__":
    unittest.main()
