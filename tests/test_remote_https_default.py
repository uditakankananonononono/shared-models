import json
import tempfile
import unittest
from pathlib import Path

from instinct_models import InklingLocal, OrnithOpenAICompat, load_config
from instinct_models.router import Router, Task


class RemoteHttpsDefaultTests(unittest.TestCase):
    def test_trusted_remote_requires_https_by_default(self):
        self.assertTrue(InklingLocal("https://models.example.com/v1", "m", trusted_remote=True).allows_private())
        self.assertFalse(InklingLocal("http://203.0.113.9:8080/v1", "m", trusted_remote=True).allows_private())

    def test_cleartext_needs_second_explicit_opt_in(self):
        p = InklingLocal("http://203.0.113.9:8080/v1", "m", trusted_remote=True, allow_cleartext_remote=True)
        self.assertTrue(p.allows_private())
        # the second switch alone does not trust a remote
        self.assertFalse(InklingLocal("http://203.0.113.9:8080/v1", "m", allow_cleartext_remote=True).allows_private())

    def test_loopback_http_unchanged(self):
        self.assertTrue(OrnithOpenAICompat("http://127.0.0.1:8080/v1", "m").allows_private())

    def test_trusted_remote_does_not_lose_loopback_http(self):
        for url in ("http://127.0.0.1:8080/v1", "http://localhost:11434/v1", "http://[::1]:8080/v1"):
            self.assertTrue(InklingLocal(url, "m", trusted_remote=True).allows_private(), url)
            self.assertTrue(OrnithOpenAICompat(url, "m", trusted_remote=True).allows_private(), url)

    def test_config_built_chain_keeps_loopback_ornith_when_trust_remote_is_on(self):
        cfg = load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_ORNITH_URL": "http://127.0.0.1:11434/v1",
                           "INSTINCT_ORNITH_MODEL": "ornith", "INSTINCT_TRUST_REMOTE": "1"})
        ornith = [p for p in Router.from_config(cfg).providers if isinstance(p, OrnithOpenAICompat)][0]
        self.assertTrue(ornith.allows_private())

    def test_env_flags_fail_closed_on_odd_values(self):
        base = {"INSTINCT_PRODUCT": "atlas"}
        for v in ("maybe", "2", "off", ""):
            c = load_config({**base, "INSTINCT_TRUST_REMOTE": v, "INSTINCT_ALLOW_CLEARTEXT_REMOTE": v})
            self.assertFalse(c.trust_remote); self.assertFalse(c.allow_cleartext_remote)

    def test_config_env_and_file_flags(self):
        base = {"INSTINCT_PRODUCT": "atlas"}
        self.assertFalse(load_config(base).allow_cleartext_remote)
        self.assertTrue(load_config({**base, "INSTINCT_ALLOW_CLEARTEXT_REMOTE": "1"}).allow_cleartext_remote)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.json"
            f.write_text(json.dumps({"trust_remote": "false", "allow_cleartext_remote": "no"}))
            c = load_config(base, path=str(f))
            self.assertFalse(c.trust_remote)  # the string "false" must not be truthy
            self.assertFalse(c.allow_cleartext_remote)
            f.write_text(json.dumps({"allow_cleartext_remote": "maybe"}))
            with self.assertRaises(ValueError):
                load_config(base, path=str(f))

    def test_router_passes_flag_and_refuses_cleartext_private_task(self):
        seen = []
        def t(url, body, headers, timeout):
            seen.append(url); return {"choices": [{"message": {"content": "hi"}}]}
        cfg = load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_INKLING_LOCAL_URL": "http://203.0.113.9:8080/v1",
                           "INSTINCT_INKLING_LOCAL_MODEL": "m", "INSTINCT_TRUST_REMOTE": "1"})
        r = Router.from_config(cfg)
        for p in r.providers:
            if isinstance(p, InklingLocal):
                p.transport = t
        out = r.run(Task([{"role": "user", "content": "x"}], private=True))
        self.assertEqual(seen, [])
        self.assertFalse(out.ok)
        cfg2 = load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_INKLING_LOCAL_URL": "http://203.0.113.9:8080/v1",
                            "INSTINCT_INKLING_LOCAL_MODEL": "m", "INSTINCT_TRUST_REMOTE": "1",
                            "INSTINCT_ALLOW_CLEARTEXT_REMOTE": "1"})
        r2 = Router.from_config(cfg2)
        for p in r2.providers:
            if isinstance(p, InklingLocal):
                p.transport = t
        r2.run(Task([{"role": "user", "content": "x"}], private=True))
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
