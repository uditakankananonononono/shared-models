import json, tempfile, unittest
from pathlib import Path
from instinct_models.training import JsonlConfirmationLog, build_needle_jsonl, evaluate_lexical

TOOL = {"name": "add_task", "description": "add", "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}


def rec(i, q, call, dec="confirmed", **kw):
    return {"id": f"r{i}", "query": q, "tools": [TOOL], "call": call, "owner_decision": dec, **kw}


class AdapterTests(unittest.TestCase):
    def test_only_confirmed_rows_reach_training_and_bad_lines_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log.jsonl"
            lines = [json.dumps(rec(1, "add task buy milk", {"name": "add_task", "arguments": {"title": "buy milk"}})),
                     json.dumps(rec(2, "add task call mom", {"name": "add_task", "arguments": {"title": "call mom"}}, dec="rejected")),
                     json.dumps(rec(3, "add task nap", {"name": "add_task", "arguments": {"title": "nap"}}, dec="unreviewed")),
                     json.dumps(rec(4, "what is the capital of France", None)),
                     json.dumps(rec(5, "add task x", {"name": "add_task", "arguments": {"title": "y"}}, product="meemee")),
                     "not json", "[1]"]
            p.write_text("\n".join(lines) + "\n")
            ds = JsonlConfirmationLog("atlas", p)
            m = build_needle_jsonl(ds, Path(d) / "out.jsonl")
            self.assertEqual(m["rows"], 2)
            self.assertEqual(m["off_topic_ratio"], 0.5)
            reasons = " ".join(x["reason"] for x in m["dropped_detail"])
            self.assertIn("not owner-confirmed", reasons)
            self.assertIn("belongs to 'meemee'", reasons)
            self.assertEqual(len(ds.skipped), 2)
            self.assertTrue(m["train_locally_only"])

    def test_unknown_product_refused(self):
        with self.assertRaises(ValueError):
            JsonlConfirmationLog("other", "x.jsonl")


class EvalTests(unittest.TestCase):
    def test_holdout_report_counts_add_up(self):
        with tempfile.TemporaryDirectory() as d:
            rows = []
            for i in range(60):
                w = f"item{i}"
                rows.append({"query": f"add task {w}", "tools": [TOOL],
                             "answers": [{"name": "add_task", "arguments": {"title": w}}]})
            for i in range(12):
                rows.append({"query": f"tell me about topic{i}", "tools": [TOOL], "answers": []})
            p = Path(d) / "t.jsonl"
            p.write_text("".join(json.dumps(r) + "\n" for r in rows))
            r = evaluate_lexical(p)
            self.assertEqual(r["train_rows"] + r["test_rows"], 72)
            self.assertEqual(r["call_exact"] + r["call_wrong_confident"] + r["call_abstained"], r["call_rows"])
            self.assertLessEqual(r["off_topic_abstained"], r["off_topic_rows"])
            print("lexical holdout:", r)
            with self.assertRaises(ValueError):
                evaluate_lexical(p, holdout_percent=0)


if __name__ == "__main__":
    unittest.main()


class PrivateLeakTests(unittest.TestCase):
    def test_non_provider_error_text_never_reaches_private_attempt(self):
        from instinct_models import Provider
        from instinct_models.router import Router, Task

        class Boom(Provider):
            name = "boom"
            def allows_private(self): return True
            def available(self): return True
            def chat(self, messages, *, tools=None, max_tokens=1024):
                raise RuntimeError("failed at http://10.0.0.5:8080/v1?key=SECRET123")

        priv = Router([Boom()]).run(Task([{"role": "user", "content": "hi"}], private=True))
        self.assertNotIn("SECRET123", str(priv.attempts))
        self.assertNotIn("10.0.0.5", str(priv.attempts))
        self.assertEqual(priv.attempts[0].outcome, "error")
        pub = Router([Boom()]).run(Task([{"role": "user", "content": "hi"}], private=False))
        self.assertIn("RuntimeError", str(pub.attempts))
