import os
import tempfile
import unittest

from instinct_models.config import PRODUCTS, load_config

ENV = {"INSTINCT_PRODUCT": PRODUCTS[0]}


def load(content, suffix=".json"):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c" + suffix)
        with open(path, "wb") as f:
            f.write(content)
        return load_config(ENV, path)


class ConfigFileErrors(unittest.TestCase):
    def test_bad_files_raise_value_error(self):
        for content, suffix in ((b"\xff\xfe{", ".json"), (b"\xff\xfe", ".yaml"), (b"a: [unclosed", ".yaml"),
                                (b"{not json", ".json")):
            with self.assertRaises(ValueError, msg=(content, suffix)):
                load(content, suffix)

    def test_good_files_still_load(self):
        self.assertEqual(load(b'{"hf_model": "m"}').hf_model, "m")
        self.assertEqual(load(b"hf_model: m\n", ".yaml").hf_model, "m")


if __name__ == "__main__":
    unittest.main()
