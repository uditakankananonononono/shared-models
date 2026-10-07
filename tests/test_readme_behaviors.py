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


class ReadmeConfigCompleteTests(unittest.TestCase):
    def test_every_env_var_in_config_is_documented(self):
        import re
        cfg = (Path(__file__).resolve().parent.parent / "instinct_models" / "config.py").read_text()
        names = set(re.findall(r'g\("([A-Z_]+)"', cfg))
        missing = sorted(n for n in names if f"instinct_{n}".lower() not in README)
        self.assertEqual(missing, [])

    def test_router_order_mentions_lexical(self):
        self.assertIn("lexical", README.split("## router", 1)[1].split("## training", 1)[0])
