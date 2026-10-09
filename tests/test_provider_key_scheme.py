import unittest

from instinct_models.providers import (HermesLocal, InklingHFRouter, InklingLocal, OpenClawOwner,
                                       OrnithOpenAICompat, ProviderUnavailable)

OK = {"choices": [{"message": {"content": "hi", "tool_calls": []}}]}


class KeySchemeTests(unittest.TestCase):
    def _spy(self):
        seen = []
        def transport(url, body, headers, timeout):
            seen.append((url, headers)); return OK
        return seen, transport

    def test_plain_http_remote_with_key_is_refused_before_transport(self):
        for cls in (InklingLocal, OrnithOpenAICompat):
            seen, t = self._spy()
            p = cls("http://203.0.113.9:8080/v1", "m", api_key="SECRET", transport=t, trusted_remote=True)
            with self.assertRaises(ProviderUnavailable) as cm:
                p.chat([{"role": "user", "content": "x"}])
            self.assertEqual(seen, [], cls.__name__)
            self.assertNotIn("SECRET", str(cm.exception))

    def test_loopback_http_and_https_with_key_still_work(self):
        for url in ("http://127.0.0.1:8080/v1", "https://models.example.com/v1"):
            seen, t = self._spy()
            r = InklingLocal(url, "m", api_key="K", transport=t, trusted_remote=True).chat([{"role": "user", "content": "x"}])
            self.assertEqual(r.text, "hi")
            self.assertEqual(seen[0][1], {"Authorization": "Bearer K"})

    def test_keyless_plain_http_remote_is_not_blocked_by_this_guard(self):
        seen, t = self._spy()
        InklingLocal("http://203.0.113.9:8080/v1", "m", transport=t, trusted_remote=True).chat([{"role": "user", "content": "x"}])
        self.assertEqual(len(seen), 1)

    def test_hf_router_and_openclaw_constructors(self):
        seen, t = self._spy()
        InklingHFRouter("m", token="HF", transport=t).chat([{"role": "user", "content": "x"}])
        self.assertTrue(seen[0][0].startswith("https://"))
        seen, t = self._spy()
        OpenClawOwner("http://127.0.0.1:18789", "tok", transport=t).chat([{"role": "user", "content": "x"}], owner_confirmed=True)
        self.assertEqual(len(seen), 1)
        with self.assertRaises(ProviderUnavailable):
            OpenClawOwner("http://203.0.113.9:18789", "tok")


if __name__ == "__main__":
    unittest.main()
