import unittest

from instinct_models.lexical import MAX_ARG_CHARS, LexicalToolModel

T = {"name": "add_task", "description": "add", "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}
GOOD = {"query": "add task buy milk", "tools": [T], "answers": [{"name": "add_task", "arguments": {"title": "buy milk"}}]}


class FitValidation(unittest.TestCase):
    def test_malformed_rows_raise_value_error_naming_the_row(self):
        bad = [{"tools": [T], "answers": []}, {"query": 5, "tools": [T], "answers": []},
               {"query": "q", "tools": None, "answers": []}, {"query": "q", "tools": [T], "answers": None},
               {"query": "q", "tools": [T], "answers": ["x"]}, {"query": "q", "tools": [T], "answers": [{"name": ["x"]}]},
               {"query": "q", "tools": [T], "answers": [{"name": "add_task", "arguments": ["x"]}]},
               {"query": "q", "tools": [{}], "answers": []}, "oops"]
        for r in bad:
            with self.assertRaisesRegex(ValueError, "training row 1"):
                LexicalToolModel().fit([GOOD, r])

    def test_valid_rows_still_train(self):
        m = LexicalToolModel().fit([GOOD] * 5)
        self.assertEqual(m.trained_rows, 5)
        self.assertEqual(m.predict("add task buy milk", [T])["name"], "add_task")


class PredictGuards(unittest.TestCase):
    def test_non_text_query_or_non_list_tools_abstain(self):
        m = LexicalToolModel().fit([GOOD] * 5)
        for q in (None, 5, ["a"]):
            self.assertIsNone(m.predict(q, [T]))
        for tools in (None, "x", {}):
            self.assertIsNone(m.predict("add task buy milk", tools))


class ArgumentCap(unittest.TestCase):
    def test_overlong_argument_is_dropped_so_a_required_one_abstains(self):
        m = LexicalToolModel().fit([GOOD] * 5)
        self.assertIsNone(m.predict("add task " + "a" * (MAX_ARG_CHARS + 1), [T]))
        r = m.predict("add task " + "a" * MAX_ARG_CHARS, [T])
        self.assertEqual(len(r["arguments"]["title"]), MAX_ARG_CHARS)


if __name__ == "__main__":
    unittest.main()
