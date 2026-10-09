import unittest

from instinct_models.lexical import LexicalToolModel

ROW = {"query": "add task a", "tools": [{"name": "t", "parameters": {"properties": {"title": {}}}}], "answers": [{"name": "t", "arguments": {"title": "a"}}]}


class SchemaShapes(unittest.TestCase):
    def test_malformed_parameter_schemas_do_not_raise(self):
        m = LexicalToolModel().fit([ROW] * 5)
        for params in ({"properties": None}, {"properties": ["x"]}, {"properties": {"a": None}}, {"required": None},
                       {"required": 5}, {"properties": {}, "required": "title"}, None, "x", []):
            r = m.predict("add task a", [{"name": "t", "parameters": params}])
            self.assertEqual(r["name"], "t", params)
            self.assertEqual(r["arguments"], {}, params)

    def test_valid_schema_still_extracts(self):
        m = LexicalToolModel().fit([ROW] * 5)
        self.assertEqual(m.predict("add task a", ROW["tools"])["arguments"], {"title": "a"})


if __name__ == "__main__":
    unittest.main()
