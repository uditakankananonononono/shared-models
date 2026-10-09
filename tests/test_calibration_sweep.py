import json, tempfile, unittest
from pathlib import Path
from instinct_models.training import calibration_sweep

T1 = {"name": "add_task", "description": "add", "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}
T2 = {"name": "add_note", "description": "note", "parameters": {"properties": {"text": {"type": "string"}}, "required": ["text"]}}


class CalibrationTests(unittest.TestCase):
    def test_sweep_accounts_for_every_row_and_is_monotone_in_abstention(self):
        rows = []
        for i in range(80):
            rows.append({"query": f"add task item{i} today", "tools": [T1, T2], "answers": [{"name": "add_task", "arguments": {"title": f"item{i}"}}]})
            rows.append({"query": f"add note idea{i} today", "tools": [T1, T2], "answers": [{"name": "add_note", "arguments": {"text": f"idea{i}"}}]})
        for i in range(20):
            rows.append({"query": f"what about topic{i} today", "tools": [T1, T2], "answers": []})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text("".join(json.dumps(r) + "\n" for r in rows))
            res = calibration_sweep(p)
        for s in res["sweep"]:
            self.assertEqual(s["served_right"] + s["served_wrong"] + s["abstained"], res["test_rows"])
        for s in res["sweep"]:
            self.assertEqual(s["abstained_off_topic_correct"] + s["abstained_missed_call"], s["abstained"])
        ab = [s["abstained"] for s in res["sweep"]]
        self.assertEqual(ab, sorted(ab))
        print("calibration (synthetic, harness check only):", res["sweep"])

    def test_empty_side_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text(json.dumps({"query": "q", "tools": [T1], "answers": []}) + "\n")
            with self.assertRaises(ValueError):
                calibration_sweep(p)


if __name__ == "__main__":
    unittest.main()
