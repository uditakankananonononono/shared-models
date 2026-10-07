import unittest
import instinct_models


class DocsHonestyTests(unittest.TestCase):
    def test_package_doc_does_not_deny_the_optional_paid_jev_route(self):
        doc = instinct_models.__doc__.lower()
        self.assertNotIn("nothing here calls a paid api", doc)
        self.assertIn("jev", doc)
        self.assertIn("off by default", doc)
