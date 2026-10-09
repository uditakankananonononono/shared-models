import json, tempfile, unittest
from pathlib import Path
from instinct_models.training import JsonlConfirmationLog, build_needle_jsonl, evaluate_lexical, calibration_sweep

TOOL = {"name": "add_task", "description": "add", "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}


class ExampleFlow(unittest.TestCase):
    def test_documented_flow_runs_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            lines = []
            for i in range(50):
                lines.append({"id": f"c{i}", "query": f"add task thing{i}", "tools": [TOOL],
                              "call": {"name": "add_task", "arguments": {"title": f"thing{i}"}}, "owner_decision": "confirmed"})
            for i in range(8):
                lines.append({"id": f"o{i}", "query": f"how is the weather in town{i}", "tools": [TOOL], "call": None, "owner_decision": "confirmed"})
            lines.append({"id": "rej", "query": "add task nope", "tools": [TOOL],
                          "call": {"name": "add_task", "arguments": {"title": "nope"}}, "owner_decision": "rejected"})
            log = d / "log.jsonl"
            log.write_text("".join(json.dumps(x) + "\n" for x in lines))
            m = build_needle_jsonl(JsonlConfirmationLog("atlas", log), d / "out" / "n.jsonl")
            self.assertEqual((m["rows"], m["dropped"]), (58, 1))
            r = evaluate_lexical(d / "out" / "n.jsonl")
            self.assertEqual(r["call_exact"] + r["call_wrong_confident"] + r["call_abstained"], r["call_rows"])
            self.assertEqual(len(calibration_sweep(d / "out" / "n.jsonl")["sweep"]), 7)


if __name__ == "__main__":
    unittest.main()
