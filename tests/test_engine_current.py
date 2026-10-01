import unittest
from types import SimpleNamespace
from instinct_models.providers import fix_needle_engine
class CurrentEngineTests(unittest.TestCase):
    def test_published_302_is_not_silently_downgraded(self):
        f=SimpleNamespace(ENGINE_VERSIONS={3:'3.0.2'})
        self.assertEqual(fix_needle_engine(f,env={}), '3.0.2')
