import tempfile
import unittest
from instinct_models.config import load_config

ENV = {"INSTINCT_PRODUCT": "atlas"}


def cfg(body):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    f.write(body); f.close()
    return load_config(ENV, f.name)


class FieldTypeTests(unittest.TestCase):
    def test_string_fields_reject_non_strings(self):
        for field in ("ornith_url", "ornith_model", "hermes_url", "hf_model", "needle_weights", "jev_api_key"):
            for bad in ("5", "[]", "{}", "true"):
                with self.assertRaises(ValueError, msg=f"{field}={bad}"):
                    cfg('{"%s": %s}' % (field, bad))

    def test_null_and_strings_are_accepted(self):
        c = cfg('{"ornith_url": null, "hermes_model": "hermes3:3b"}')
        self.assertIsNone(c.ornith_url)
        self.assertEqual(c.hermes_model, "hermes3:3b")
