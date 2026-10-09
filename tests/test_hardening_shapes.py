import unittest

from instinct_models.lexical import LexicalToolModel
from instinct_models.providers import ChatResult
from instinct_models.router import Router, Task
from tests.test_router_result_guard import GOOD, MSG, T, Fake
from tests.test_lexical_schema_shapes import ROW, TOOL


class LexicalSchemaCrashes(unittest.TestCase):
    def test_remaining_malformed_schema_shapes_do_not_raise(self):
        m = LexicalToolModel().fit([ROW] * 5)
        for params in ({"properties": {}, "required": [["a"]]}, {"properties": {"a": {"enum": 5}}},
                       {"properties": {"a": {"enum": "abc"}}}, {"properties": {1: {}}}, {"properties": {(1, 2): None}}):
            r = m.predict("add task buy milk", [{"name": "t", "parameters": params}])
            self.assertEqual(r["name"], "t", params)

    def test_non_text_required_entry_is_ignored_text_one_still_abstains(self):
        m = LexicalToolModel().fit([ROW] * 5)
        p = {"properties": {}, "required": [["a"], "missing"]}
        self.assertIsNone(m.predict("add task buy milk", [{"name": "t", "parameters": p}]))

    def test_valid_schema_unchanged(self):
        m = LexicalToolModel().fit([ROW] * 5)
        self.assertEqual(m.predict("add task buy milk", [TOOL])["arguments"], {"title": "buy milk"})


class RouterResultShapes(unittest.TestCase):
    def test_remaining_malformed_results_escalate(self):
        bad = [ChatResult("b", "m", "t", [None], {}), ChatResult("b", "m", "t", [{"arguments": {}}], {}),
               ChatResult("b", "m", "t", [{"name": ""}], {}), ChatResult("b", "m", "t", ["x"], {}),
               ChatResult("b", "m", None, [], {})]
        for b in bad:
            for tools in (None, T):
                out = Router([Fake("bad", b), Fake("good", GOOD)]).run(Task(MSG, tools))
                self.assertEqual([a.outcome for a in out.attempts], ["error", "ok"], (b, tools))

    def test_wellformed_results_still_pass(self):
        out = Router([Fake("good", GOOD)]).run(Task(MSG, T))
        self.assertEqual(out.attempts[0].outcome, "ok")
        out = Router([Fake("g", ChatResult("g", "m", "hi", [], {}))]).run(Task(MSG, None))
        self.assertTrue(out.ok)


if __name__ == "__main__":
    unittest.main()
