import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from instinct_models import LexicalLocal, LexicalToolModel, Router, Task, load_config
from instinct_models.training import ExampleRow, build_needle_jsonl

T_OBL = {"name": "log_obligation", "description": "record that a party owes something by a date",
         "parameters": {"type": "object", "properties": {"party": {"type": "string"}, "due": {"type": "string"}}, "required": ["party"]}}
T_EXP = {"name": "add_expense", "description": "record a spend amount",
         "parameters": {"type": "object", "properties": {"amount": {"type": "number"}, "vendor": {"type": "string"}}, "required": ["amount"]}}
TOOLS = [T_OBL, T_EXP]
Q = [("Log that Acme owes us a report due 2026-11-02", [("log_obligation", {"party": "Acme", "due": "2026-11-02"})]),
     ("Log that Globex owes us a contract due 2026-12-01", [("log_obligation", {"party": "Globex", "due": "2026-12-01"})]),
     ("Add an expense of 45 paid to Uber", [("add_expense", {"amount": 45, "vendor": "Uber"})]),
     ("Add an expense of 12.5 paid to Staples", [("add_expense", {"amount": 12.5, "vendor": "Staples"})]),
     ("Record expense 80 paid to Delta", [("add_expense", {"amount": 80, "vendor": "Delta"})]),
     ("What is the weather like in Paris", []), ("Tell me a joke about cats", []), ("Who won the match yesterday", [])]


def rows():
    return [{"query": q, "tools": TOOLS, "answers": [{"name": n, "arguments": a} for n, a in c]} for q, c in Q]


class LexicalTests(unittest.TestCase):
    def setUp(self): self.m = LexicalToolModel().fit(rows())

    def test_different_queries_pick_different_tools_and_args(self):
        a = self.m.predict("Log that Initech owes us a deck due 2027-01-15", TOOLS)
        b = self.m.predict("Add an expense of 99 paid to Lyft", TOOLS)
        self.assertEqual((a["name"], a["arguments"]), ("log_obligation", {"party": "Initech", "due": "2027-01-15"}))
        self.assertEqual((b["name"], b["arguments"]["amount"], b["arguments"]["vendor"]), ("add_expense", 99, "Lyft"))

    def test_abstains_off_topic(self):
        self.assertIsNone(self.m.predict("What is the capital of Peru", TOOLS))

    def test_arguments_are_literal_substrings(self):
        q = "Log that Hooli owes us a cheque due 2027-03-03"
        for v in self.m.predict(q, TOOLS)["arguments"].values():
            self.assertIn(str(v), q)

    def test_training_changes_behaviour(self):
        untrained = LexicalToolModel()
        self.assertIsNone(untrained.predict("Add an expense of 5 paid to Uber", TOOLS))
        self.assertFalse(LexicalLocal(untrained).available())

    def test_missing_required_arg_abstains(self):
        self.assertIsNone(self.m.predict("Add an expense paid to Uber", TOOLS))

    def test_provider_never_writes_prose_and_needs_tools(self):
        p = LexicalLocal(self.m)
        r = p.chat([{"role": "user", "content": "Add an expense of 7 paid to Uber"}], tools=TOOLS)
        self.assertEqual(r.text, "")
        self.assertEqual(r.tool_calls[0]["name"], "add_expense")
        from instinct_models import ProviderUnavailable
        with self.assertRaises(ProviderUnavailable):
            p.chat([{"role": "user", "content": "hi"}])

    def test_router_from_config_gives_real_answer_with_no_servers(self):
        class DS:
            product = "atlas"
            def rows(self):
                return [ExampleRow(q, TOOLS, [{"name": n, "arguments": a} for n, a in c], True, f"t{i}") for i, (q, c) in enumerate(Q)]
        with tempfile.TemporaryDirectory() as d:
            build_needle_jsonl(DS(), f"{d}/t.jsonl")
            cfg = load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_LEXICAL_TRAIN_JSONL": f"{d}/t.jsonl"})
            out = Router.from_config(cfg).run(Task([{"role": "user", "content": "Add an expense of 30 paid to Bolt"}], tools=TOOLS))
        self.assertTrue(out.ok)
        self.assertEqual(out.result.tool_calls, [{"name": "add_expense", "arguments": {"amount": 30, "vendor": "Bolt"}}])
        self.assertEqual(out.result.provider, "lexical-local")

    def test_no_model_configured_is_reported_not_faked(self):
        out = Router.from_config(load_config({"INSTINCT_PRODUCT": "atlas"})).run(Task([{"role": "user", "content": "hi"}]))
        self.assertFalse(out.ok)
        self.assertTrue(all(a.outcome in ("skipped", "unavailable") for a in out.attempts))

if __name__ == "__main__":
    unittest.main()
