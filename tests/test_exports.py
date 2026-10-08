import unittest
import instinct_models


class ExportTests(unittest.TestCase):
    def test_every_component_in_readme_table_is_importable_from_top_level(self):
        for name in ("AILibraryCatalog", "CatalogItem", "CatalogSource", "JevEval", "NeedleLocal", "OrnithOpenAICompat",
                     "InklingLocal", "InklingHFRouter"):
            self.assertTrue(hasattr(instinct_models, name), name)
            self.assertIn(name, instinct_models.__all__, name)
