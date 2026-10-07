import unittest
from instinct_models.providers import NeedleLocal

TOOLS = [{"name": "t", "description": "d", "parameters": {"properties": {}}}]


class Agent:
    def __init__(self, sink, **kw):
        self.sink = sink

    def complete(self, query, max_new_tokens=256):
        self.sink.append(query)
        return {"success": True, "type": "text"}


class NeedleInputTests(unittest.TestCase):
    def _run(self, content):
        seen = []
        NeedleLocal(factory=lambda **kw: Agent(seen, **kw)).chat([{"role": "user", "content": content}], tools=TOOLS)
        return seen[0]

    def test_null_content_becomes_empty_string(self):
        self.assertEqual(self._run(None), "")

    def test_parts_list_is_flattened_to_text(self):
        self.assertEqual(self._run([{"type": "text", "text": "add task"}, {"type": "text", "text": "now"}]), "add task now")

    def test_plain_string_unchanged(self):
        self.assertEqual(self._run("hi"), "hi")
