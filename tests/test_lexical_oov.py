import json
import tempfile
import unittest
from instinct_models.lexical import LexicalToolModel

TOOL = {"name": "add_task", "description": "d", "parameters": {"properties": {"title": {"type": "string"}}}}


def model():
    return LexicalToolModel().fit([{"query": "add task buy milk", "tools": [{"name": "add_task", "description": "d"}],
                                    "answers": [{"name": "add_task", "arguments": {"title": "buy milk"}}]}])


def load(body):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write(body); f.close()
    return LexicalToolModel.from_jsonl(f.name)


class OovTests(unittest.TestCase):
    def test_query_with_no_known_words_abstains(self):
        self.assertIsNone(model().predict("purple elephant dance", [TOOL]))

    def test_known_words_still_predict(self):
        self.assertEqual(model().predict("add task buy bread", [TOOL])["name"], "add_task")


class JsonlErrorTests(unittest.TestCase):
    def test_bad_line_names_the_line(self):
        for body in ('{"query":"a"}\nnot json\n', '[1]\n', '{"answers":[]}\n'):
            with self.assertRaises(ValueError) as cm:
                load(body)
            self.assertIn("line", str(cm.exception))
