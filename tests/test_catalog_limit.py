import unittest
from instinct_models.catalog import AILibraryCatalog

HTML = '<a href="/tools/a">Tool A</a><a href="/tools/b">Tool B</a>'


def cat():
    def fetch(url):
        return "User-agent: *\nAllow: /" if url.endswith("robots.txt") else HTML
    return AILibraryCatalog(fetch=fetch, min_interval_s=0)


class LimitTests(unittest.TestCase):
    def test_nonpositive_limit_returns_nothing(self):
        for n in (0, -1):
            self.assertEqual(cat().browse("", limit=n), [], n)

    def test_limit_caps_results(self):
        self.assertEqual(len(cat().browse("", limit=1)), 1)
