import json
import os
import tempfile
import unittest

from instinct_models.training.evaluate import calibration_sweep, evaluate_lexical
from instinct_models.training.needle_lora import NeedleLoRAJob, train_needle_lora

T = {"name": "t", "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}


class Done:
    returncode, stdout, stderr = 0, "", ""


class Evaluate(unittest.TestCase):
    def path(self, lines):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "e.jsonl")
        open(p, "w").write("\n".join(lines))
        return p

    def test_bad_rows_raise_value_error_with_line(self):
        for bad in ('{"tools": []}', "5", "{bad", '{"query": 5, "tools": [], "answers": []}', '{"query": "q", "tools": []}'):
            for fn in (evaluate_lexical, calibration_sweep):
                with self.assertRaisesRegex(ValueError, "line 2"):
                    fn(self.path([json.dumps({"query": "a", "tools": [T], "answers": []}), bad]))

    def test_good_file_still_evaluates(self):
        rows = [json.dumps({"query": f"add task {i}", "tools": [T], "answers": [{"name": "t", "arguments": {"title": str(i)}}]}) for i in range(40)]
        self.assertEqual(evaluate_lexical(self.path(rows))["train_rows"] + evaluate_lexical(self.path(rows))["test_rows"], 40)


class NeedleJob(unittest.TestCase):
    def run_job(self, manifest=None, **kw):
        d = tempfile.mkdtemp()
        data = os.path.join(d, "t.jsonl")
        open(data, "w").write("{}\n")
        if manifest is not None:
            open(data + ".manifest.json", "w").write(manifest)
        calls = []

        def runner(cmd, env):
            calls.append(cmd)
            if cmd[1] == "build":
                open(cmd[-1], "w").write("w")
            return Done()

        out = os.path.join(d, "o")
        return train_needle_lora(NeedleLoRAJob("x", data, out, **kw), runner=runner), calls

    def test_bad_manifest_and_bad_parameters_raise_before_running(self):
        for kw in ({"manifest": "[1]"}, {"manifest": "null"}, {"manifest": "{bad"}, {"epochs": -3}, {"epochs": "x"}, {"epochs": True},
                   {"val_split": 5}, {"val_split": float("nan")}, {"val_split": "0.1"}, {"base_checkpoint": "--upload"}, {"base_checkpoint": ""}):
            with self.assertRaises(ValueError, msg=kw):
                self.run_job(**kw)

    def test_valid_job_still_runs(self):
        rec, calls = self.run_job(epochs=2, val_split=0.2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(rec["epochs"], 2)


if __name__ == "__main__":
    unittest.main()
