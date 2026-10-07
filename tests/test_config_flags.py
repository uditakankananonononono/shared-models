import unittest
from instinct_models.config import load_config


class AllowHostedParsingTests(unittest.TestCase):
    def _hosted(self, v):
        return load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_ALLOW_HOSTED": v}).allow_hosted

    def test_falsey_spellings_keep_metered_route_off(self):
        for v in ("0", "false", "False", "FALSE", "no", "No", "off", "OFF", " false ", "n"):
            self.assertFalse(self._hosted(v), v)

    def test_truthy_spellings_enable(self):
        for v in ("1", "true", "True", "yes", "on"):
            self.assertTrue(self._hosted(v), v)

    def test_unrecognized_value_stays_off(self):
        self.assertFalse(self._hosted("maybe"))
