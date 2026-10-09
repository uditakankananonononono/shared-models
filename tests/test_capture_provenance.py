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

    def _hold(self, path):
        """A child process (descendant of this test process) that holds `path` open."""
        import subprocess
        import sys
        c = subprocess.Popen([sys.executable, "-c", "import sys,time;f=open(sys.argv[1],'rb');print('ready',flush=True);time.sleep(60)", path],
                             stdout=subprocess.PIPE)
        self.addCleanup(lambda: (c.kill(), c.wait(), c.stdout.close()))
        c.stdout.readline()
        return c.pid

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "Linux /proc needed")
    def test_binding_confirmed_needs_hash_exact_inode_and_port_link(self):
        p, d = self.weights()
        exp = {os.path.basename(p): d}
        with open(p, "rb"):
            r = cp.capture(self.url, "fake-model", [p], exp, pid=os.getpid())  # this process serves the port and holds the file
            self.assertEqual(r["binding"]["verdict"], "confirmed", r["binding"])
            self.assertEqual(r["binding"]["pid_port_relation"], "same")
            r = cp.capture(self.url, "fake-model", [p], None, pid=os.getpid())  # no expected hash: never confirmed
            self.assertEqual(r["binding"]["verdict"], "unverified")
            self.assertIn("expect-sha256", r["binding"]["reason"])
            self.assertFalse(r["all_requested_checks_passed"])
        r = cp.capture(self.url, "fake-model", [p], exp, pid=os.getpid())  # file closed
        self.assertEqual(r["binding"]["verdict"], "unverified")
        r = cp.capture(self.url, "fake-model", [p], exp, pid=2 ** 22 + 12345)  # no such process
        self.assertEqual(r["binding"]["verdict"], "unverified")
        self.assertIsNotNone(r["binding"]["process_error"])

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "Linux /proc needed")
    def test_runner_child_of_the_listener_is_accepted(self):
        p, d = self.weights()
        child = self._hold(p)  # Ollama shape: the server owns the port, a child process holds the weights
        r = cp.capture(self.url, "fake-model", [p], {os.path.basename(p): d}, pid=child)
        self.assertEqual(r["binding"]["pid_port_relation"], "pid_is_descendant_of_listener")
        self.assertEqual(r["binding"]["verdict"], "confirmed", r["binding"])

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "Linux /proc needed")
    def test_file_replaced_after_open_is_never_confirmed(self):
        p, d = self.weights(b"OLD weights")
        with open(p, "rb"):
            new = p + ".new"
            open(new, "wb").write(b"NEW weights")
            os.replace(new, p)  # the process still holds the OLD inode, shown as "(deleted)"
            nd = hashlib.sha256(b"NEW weights").hexdigest()
            r = cp.capture(self.url, "fake-model", [p], {os.path.basename(p): nd}, pid=os.getpid())
            self.assertEqual(r["binding"]["verdict"], "unverified", r["binding"])
            self.assertTrue(r["binding"]["stale_or_replaced"])
            self.assertTrue(r["weights"]["files"][0]["matches_expected"])  # file identity alone was fine: binding is what failed

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "Linux /proc needed")
    def test_pid_not_tied_to_the_listening_port_is_unverified(self):
        import subprocess
        import sys
        code = ("import http.server,os;s=http.server.HTTPServer(('127.0.0.1',0),http.server.BaseHTTPRequestHandler);"
                "print(os.getpid(),s.server_address[1],flush=True);s.serve_forever()")
        # the shell exits at once, so the listener is orphaned and unrelated to this process
        o = subprocess.Popen(["sh", "-c", f"{sys.executable} -c \"{code}\" &"], stdout=subprocess.PIPE)
        lpid, lport = (int(x) for x in o.stdout.readline().split())
        self.addCleanup(lambda: (os.kill(lpid, 9), o.wait(), o.stdout.close()))
        p, d = self.weights()
        with open(p, "rb"):
            r = cp.capture(f"http://127.0.0.1:{lport}/v1", None, [p], {os.path.basename(p): d}, pid=os.getpid())
        self.assertEqual(r["binding"]["pid_port_relation"], "unrelated")
        self.assertEqual(r["binding"]["verdict"], "unverified")
        self.assertIn("operator-asserted", r["binding"]["reason"])

    def test_redirects_are_not_followed(self):
        class R(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", Capture.url + "/models")
                self.send_header("Content-Length", "0")
                self.end_headers()

        srv = HTTPServer(("127.0.0.1", 0), R)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        r = cp.capture(f"http://127.0.0.1:{srv.server_address[1]}/v1", "fake-model", [])
        self.assertFalse(r["checks"]["reachable"])
        self.assertEqual(r["reachability"]["get_models_status"], 302)

    def test_checks_are_never_empty_so_nothing_passes_vacuously(self):
        r = cp.capture("http://127.0.0.1:1/v1", None, [])
        self.assertTrue(r["checks"])
        self.assertFalse(r["all_requested_checks_passed"])

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
