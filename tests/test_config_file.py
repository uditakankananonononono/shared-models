import tempfile
import unittest
from instinct_models.config import load_config

ENV = {"INSTINCT_PRODUCT": "atlas"}


def cfg(body):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    f.write(body); f.close()
    return load_config(ENV, f.name)


class ConfigFileTests(unittest.TestCase):
    def test_string_false_in_file_keeps_hosted_off(self):
        for v in ('"false"', '"0"', '"no"', '"off"', "false", "0"):
            self.assertFalse(cfg('{"allow_hosted": %s}' % v).allow_hosted, v)

    def test_true_spellings_in_file_enable(self):
        for v in ('"true"', '"1"', "true"):
            self.assertTrue(cfg('{"allow_hosted": %s}' % v).allow_hosted, v)

    def test_unrecognized_hosted_value_is_rejected(self):
        for v in ('"maybe"', "[]", "2"):
            with self.assertRaises(ValueError):
                cfg('{"allow_hosted": %s}' % v)

    def test_file_cannot_switch_product(self):
        with self.assertRaises(ValueError):
            cfg('{"product": "meemee"}')
        self.assertEqual(cfg('{"product": "atlas"}').product, "atlas")

    def test_non_object_file_is_a_value_error(self):
        with self.assertRaises(ValueError):
            cfg("[1]")

    def test_invalid_json_file_is_a_value_error(self):
        with self.assertRaises(ValueError):
            cfg("{")
