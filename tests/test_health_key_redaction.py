import unittest

from instinct_models.health import hf_token_valid, probe

SECRET = "sk-SECRET\nvalue"


class KeyNotEchoed(unittest.TestCase):
    def test_bad_key_characters_never_appear_in_results(self):
        for key in (SECRET, "sk-SECRET value", "sk-SECRÉT", "sk-SECRET\x00"):
            out = probe("http://127.0.0.1:1", "m", key)
            self.assertIs(out["ok"], False)
            self.assertNotIn("SECR", str(out))
            self.assertNotIn("SECR", str(hf_token_valid(key, timeout=1)))

    def test_normal_key_still_sent_to_loopback(self):
        out = probe("http://127.0.0.1:1", "m", "sk-normal-key")
        self.assertIs(out["ok"], False)
        self.assertNotIn("normal-key", str(out))


if __name__ == "__main__":
    unittest.main()
