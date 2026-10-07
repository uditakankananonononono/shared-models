import unittest
from instinct_models.providers import HermesLocal
from instinct_models.router import Router, Task


class HermesAvailabilityTests(unittest.TestCase):
    def test_nonloopback_url_is_unavailable_not_an_exception(self):
        for u in ("https://evil.example/v1", "http://localhost/v1", "http://user:p@127.0.0.1:11434/v1"):
            self.assertFalse(HermesLocal(u, "m").available(), u)

    def test_router_skips_misconfigured_hermes(self):
        r = Router([HermesLocal("https://evil.example/v1", "m")]).run(Task([{"role": "user", "content": "x"}]))
        self.assertFalse(r.ok)
        self.assertEqual(r.attempts[0].outcome, "unavailable")

    def test_loopback_url_is_available(self):
        self.assertTrue(HermesLocal("http://127.0.0.1:11434/v1", "m").available())
