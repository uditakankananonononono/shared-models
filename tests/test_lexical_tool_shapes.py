import unittest
from instinct_models.lexical import LexicalToolModel

GOOD = {"name": "add_task", "description": "d"}


def model():
    return LexicalToolModel().fit([{"query": "add task buy milk", "tools": [GOOD],
                                    "answers": [{"name": "add_task", "arguments": {"title": "buy milk"}}]}])


class MalformedToolTests(unittest.TestCase):
    def test_nameless_tool_is_ignored_not_a_crash(self):
        r = model().predict("add task x", [{"description": "x"}, GOOD])
        self.assertEqual(r["name"], "add_task")

    def test_non_dict_property_spec_is_tolerated(self):
        t = {"name": "add_task", "parameters": {"properties": {"t": None}, "required": []}}
        self.assertEqual(model().predict("add task x", [t])["name"], "add_task")

    def test_non_dict_tool_entry_is_ignored(self):
        self.assertEqual(model().predict("add task x", ["junk", GOOD])["name"], "add_task")
