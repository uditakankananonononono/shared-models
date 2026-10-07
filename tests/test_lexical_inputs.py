import unittest
from instinct_models.lexical import LexicalLocal, LexicalToolModel

TOOL = {"name": "add_task", "description": "add",
        "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}


def model():
    return LexicalToolModel().fit([{"query": "add task buy milk", "tools": [TOOL],
                                    "answers": [{"name": "add_task", "arguments": {"title": "buy milk"}}]}])


class LexicalInputTests(unittest.TestCase):
    def test_null_content_abstains_instead_of_crashing(self):
        r = LexicalLocal(model()).chat([{"role": "user", "content": None}], tools=[TOOL])
        self.assertEqual(r.tool_calls, [])

    def test_content_parts_list_is_read_as_text(self):
        msgs = [{"role": "user", "content": [{"type": "text", "text": "add task buy milk"}]}]
        r = LexicalLocal(model()).chat(msgs, tools=[TOOL])
        self.assertEqual(r.tool_calls[0]["name"], "add_task")

    def test_integer_param_rejects_decimal(self):
        t = {"name": "x", "parameters": {"properties": {"n": {"type": "integer"}}}}
        self.assertEqual(model().extract("take 3.5 items", t), {})
