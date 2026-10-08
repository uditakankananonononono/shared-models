import unittest
from instinct_models.providers import (HermesLocal, JevEval, OpenClawOwner, ProviderError, ProviderUnavailable,
                                       require_loopback_url)
from instinct_models.training.dataset import ExampleRow, check_row


class SweepTests(unittest.TestCase):
    def test_bad_port_is_provider_unavailable(self):
        for u in ("http://localhost:abc/v1", "http://127.0.0.1:99999/v1"):
            with self.assertRaises(ProviderUnavailable):
                require_loopback_url(u)
            self.assertFalse(HermesLocal(u, "m").available(), u)

    def test_blank_openclaw_token_rejected(self):
        with self.assertRaises(ProviderUnavailable):
            OpenClawOwner("http://127.0.0.1:1", "   ")

    def test_jev_answers_must_be_an_object(self):
        j = JevEval(gateway_api_key="k", transport=lambda *a: {"answers": "junk"})
        with self.assertRaises(ProviderError):
            j.evaluate("s", {"a": {"type": "noul", "instructions": "x"}})

    def test_dataset_rejects_malformed_tools_and_answers(self):
        for tools, answers in ((None, []), (["junk"], []), ([{"name": "t"}], ["junk"])):
            self.assertIsNotNone(check_row(ExampleRow("q", tools, answers, True, "x")), (tools, answers))
