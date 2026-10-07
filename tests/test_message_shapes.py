import unittest
from instinct_models.lexical import LexicalLocal, LexicalToolModel
from instinct_models.providers import NeedleLocal

TOOL = {"name": "add_task", "description": "d"}


class Agent:
    def complete(self, query, max_new_tokens=256):
        return {"success": True, "type": "text"}


class NonDictMessageTests(unittest.TestCase):
    def test_needle_ignores_non_dict_messages(self):
        n = NeedleLocal(factory=lambda **k: Agent())
        for msgs in ([None], ["str"], [None, {"role": "user", "content": "hi"}]):
            self.assertEqual(n.chat(msgs, tools=[TOOL]).tool_calls, [])

    def test_lexical_ignores_non_dict_messages(self):
        m = LexicalToolModel().fit([{"query": "add task buy milk", "tools": [TOOL],
                                     "answers": [{"name": "add_task", "arguments": {}}]}])
        for msgs in ([None], ["str"]):
            self.assertEqual(LexicalLocal(m).chat(msgs, tools=[TOOL]).tool_calls, [])
