import unittest

from instinct_models.lexical import LexicalToolModel

TOOL = {"name": "t", "description": "add", "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}
ROW = {"query": "add task buy milk", "tools": [TOOL], "answers": [{"name": "t", "arguments": {"title": "buy milk"}}]}


class SchemaShapes(unittest.TestCase):
    def test_malformed_parameter_schemas_do_not_raise(self):
        m = LexicalToolModel().fit([ROW] * 5)
        for params in ({"properties": None}, {"properties": ["x"]}, {"properties": {"a": None}}, {"required": None},
                       {"required": 5}, {"properties": {}, "required": "title"}, None, "x", []):
            r = m.predict("add task buy milk", [{"name": "t", "parameters": params}])
            self.assertEqual(r["name"], "t", params)
            self.assertEqual(r["arguments"], {}, params)

    def test_valid_schema_still_extracts(self):
        m = LexicalToolModel().fit([ROW] * 5)
        self.assertEqual(m.predict("add task buy milk", [TOOL])["arguments"], {"title": "buy milk"})


if __name__ == "__main__":
    unittest.main()
