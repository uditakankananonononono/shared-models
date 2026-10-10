"""Static checks on the serving scripts. They read text only; nothing here runs a server, build or pull (UNRUN)."""
import re
import unittest
from pathlib import Path

S = Path(__file__).resolve().parent.parent / "scripts" / "inkling"


class ServingPinTests(unittest.TestCase):
    def test_no_silent_failure_fallback(self):
        for name in ("serve_llamacpp.sh", "serve_vllm.sh"):
            self.assertNotIn("|| true", (S / name).read_text(), name)

    def test_llamacpp_pins_a_full_sha_and_asserts_it(self):
        t = (S / "serve_llamacpp.sh").read_text()
        self.assertRegex(t, r'PIN_SHA="[0-9a-f]{40}"')
        self.assertIn('"$PIN_SHA"', t)

    def test_vllm_image_is_digest_pinned_not_floating(self):
        t = (S / "serve_vllm.sh").read_text()
        code = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn(":nightly", code)
        self.assertRegex(t, r"vllm/vllm-openai:v[0-9.]+@sha256:[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main()
