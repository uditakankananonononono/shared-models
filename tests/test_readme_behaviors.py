import unittest
from pathlib import Path

README = (Path(__file__).resolve().parent.parent / "README.md").read_text().lower()


class ReadmeBehaviorTests(unittest.TestCase):
    def test_documents_redirect_refusal(self):
        self.assertIn("redirect", README)

    def test_documents_malformed_response_handling(self):
        self.assertIn("providererror", README)
        self.assertIn("malformed", README)

    def test_documents_catalog_scheme_and_domain_rules(self):
        self.assertIn("http/https", README)
        self.assertIn("dot-delimited", README)
