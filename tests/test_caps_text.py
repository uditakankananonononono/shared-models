"""Text-only checks (read files, never import or run the product). Hold with the proposal unapplied."""
import pathlib, re, unittest
R = pathlib.Path(__file__).resolve().parent.parent
DOC = (R / "docs/provider-response-caps-contract.md").read_text()
PATCH = (R / "proposals/sm-caps.patch").read_text()


class CapsText(unittest.TestCase):
    def test_patch_scope_is_three_files(self):
        self.assertEqual(sorted(re.findall(r"^diff --git a/(\S+)", PATCH, re.M)), ["instinct_models/health.py", "instinct_models/providers.py", "tests/test_jev_hardening.py"])

    def test_patch_has_no_unbounded_read_left(self):
        self.assertNotRegex(PATCH, r"^\+.*\.read\(\)")
        self.assertIn("read1(", PATCH)

    def test_defaults_documented(self):
        for s in ("8 MiB", "64 MiB", "max_response_bytes", "max_bytes", "NOT traced", "3.12", "chunked", "proxy_bypass"):
            self.assertIn(s, DOC)

    def test_every_trace_source_url_cited(self):
        for u in ("https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/urllib/request.py",
                  "https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/http/client.py",
                  "https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/socket.py",
                  "https://raw.githubusercontent.com/python/cpython/v3.12.0/Modules/socketmodule.c",
                  "https://docs.python.org/3.12/library/socket.html"):
            self.assertIn(u, DOC)

    def test_errors_are_generic_in_patch(self):
        self.assertIn('ProviderError("provider response too large")', PATCH)
        self.assertIn('ProviderError("provider response too slow")', PATCH)

    def test_terminal_read_deadline_and_chunked_limit_documented(self):
        self.assertGreaterEqual(PATCH.count("if clock() > deadline:"), 4)
        self.assertIn("timeout plus one per-operation window", DOC)
        self.assertIn("NON-chunked", DOC)
        self.assertIn("_read1_chunked", DOC)
        self.assertIn("_get_chunk_left", DOC)

    def test_openclaw_wired_and_health_validated(self):
        self.assertIn("transport is _openclaw_http", PATCH)
        self.assertIn("return http_json(url, body, headers, timeout, max_bytes)", PATCH)
        self.assertIn("max_bytes must be a positive integer", PATCH)

    def test_direct_entry_points_validate_first(self):
        self.assertEqual(PATCH.count("+    _check_max_bytes(max_bytes)  # before any request or network use"), 3)

    def test_jev_fixture_uses_read1_and_assertions_not_weakened(self):
        self.assertIn("+    def read1(self, n=-1):", PATCH)
        removed = [l for l in PATCH.splitlines() if l.startswith("-") and "assert" in l]
        self.assertEqual(removed, [])

    def test_doc_labels_unproven(self):
        self.assertIn("UNPROVEN", DOC); self.assertIn("authored, not run", DOC)


if __name__ == "__main__":
    unittest.main()
