"""The Jev key and unknown config-file keys must not appear in ProductConfig's repr/str; storage is unchanged.
Not covered by design: dataclasses.asdict and dataclasses.replace still carry the values."""
import json
import tempfile
import unittest
from pathlib import Path

from instinct_models.config import ProductConfig, load_config

ENV = {"INSTINCT_PRODUCT": "atlas"}
KEY_ENV, KEY_FILE, EXTRA_SECRET = "sk-env-synthetic-123", "sk-file-synthetic-456", "extra-secret-synthetic-789"


def from_file(body: dict):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.json"
        p.write_text(json.dumps(body))
        return load_config(ENV, str(p))


class ConfigReprTests(unittest.TestCase):
    def test_env_key_is_stored_but_not_in_repr_or_str(self):
        c = load_config({**ENV, "INSTINCT_JEV_API_KEY": KEY_ENV})
        self.assertEqual(c.jev_api_key, KEY_ENV)
        self.assertNotIn(KEY_ENV, repr(c))
        self.assertNotIn(KEY_ENV, str(c))
        self.assertNotIn("jev_api_key", repr(c))

    def test_file_key_and_extra_are_stored_but_not_in_repr(self):
        c = from_file({"jev_api_key": KEY_FILE, "some_token": EXTRA_SECRET})
        self.assertEqual(c.jev_api_key, KEY_FILE)
        self.assertEqual(c.extra, {"some_token": EXTRA_SECRET})
        for secret in (KEY_FILE, EXTRA_SECRET):
            self.assertNotIn(secret, repr(c))
            self.assertNotIn(secret, str(c))
        self.assertNotIn("extra=", repr(c))

    def test_directly_constructed_config_keeps_the_same_rule(self):
        c = ProductConfig(product="atlas", jev_api_key=KEY_ENV, extra={"k": EXTRA_SECRET})
        self.assertNotIn(KEY_ENV, repr(c))
        self.assertNotIn(EXTRA_SECRET, repr(c))

    def test_other_fields_still_appear_in_repr(self):
        c = load_config({**ENV, "INSTINCT_ORNITH_MODEL": "tag-synthetic"})
        self.assertIn("product='atlas'", repr(c))
        self.assertIn("tag-synthetic", repr(c))

    def test_equality_and_field_order_unchanged(self):
        a = load_config({**ENV, "INSTINCT_JEV_API_KEY": "k1"})
        b = load_config({**ENV, "INSTINCT_JEV_API_KEY": "k2"})
        self.assertNotEqual(a, b)  # repr=False does not change compare
        names = list(ProductConfig.__dataclass_fields__)
        self.assertEqual(names[-2:], ["jev_api_key", "extra"])


class ReadmeKeyClaimTests(unittest.TestCase):
    README = (Path(__file__).resolve().parent.parent / "README.md").read_text()

    def test_unsupported_never_stored_claim_is_gone(self):
        self.assertNotIn("never stored", self.README)

    def test_readme_states_memory_and_repr_scope(self):
        low = self.README.lower()
        self.assertIn("runtime memory", low)
        self.assertIn("repr", low)
        self.assertIn("asdict", low)


if __name__ == "__main__":
    unittest.main()
