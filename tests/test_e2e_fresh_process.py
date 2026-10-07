import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = {"name": "add_task", "description": "add a task",
        "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}
ROWS = [{"query": "add task buy milk", "tools": [TOOL], "answers": [{"name": "add_task", "arguments": {"title": "buy milk"}}]},
        {"query": "add task call mom", "tools": [TOOL], "answers": [{"name": "add_task", "arguments": {"title": "call mom"}}]},
        {"query": "what is the capital of France", "tools": [TOOL], "answers": []}]
CODE = """
import json, sys
from instinct_models.config import load_config
from instinct_models.router import Router, Task
cfg = load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_LEXICAL_TRAIN_JSONL": sys.argv[1]})
tool = json.loads(sys.argv[2])
out = []
for q in ("add task water plants", "what is the capital of France"):
    r = Router.from_config(cfg).run(Task([{"role": "user", "content": q}], tools=[tool], private=True))
    out.append({"ok": r.ok, "calls": r.result.tool_calls if r.result else None, "last": r.attempts[-1].outcome})
print(json.dumps(out))
"""


class FreshProcessE2E(unittest.TestCase):
    def test_lexical_floor_serves_a_private_task_and_abstains_on_offtopic(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.jsonl"
            f.write_text("".join(json.dumps(r) + "\n" for r in ROWS))
            env = {k: v for k, v in os.environ.items() if not k.startswith(("INSTINCT_", "HF_"))}
            env["PYTHONPATH"] = str(ROOT)
            p = subprocess.run([sys.executable, "-c", CODE, str(f), json.dumps(TOOL)], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr)
            a, b = json.loads(p.stdout)
            self.assertTrue(a["ok"])
            self.assertEqual(a["calls"], [{"name": "add_task", "arguments": {"title": "water plants"}}])
            self.assertFalse(b["ok"])
            self.assertEqual(b["last"], "escalated")
