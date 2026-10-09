import tempfile
import unittest
from pathlib import Path

from instinct_models.training import ExampleRow, build_needle_jsonl

T = {"name": "t", "parameters": {}}


class _D:
    product = "atlas"
    def __init__(self, rows): self._r = rows
    def rows(self): return self._r


def _row(ref, **kw):
    base = dict(query="x", tools=[T], answers=[], confirmed=True, source_ref=ref)
    base.update(kw)
    return ExampleRow(**base)


class DatasetTypeTests(unittest.TestCase):
    def _build(self, bad):
        with tempfile.TemporaryDirectory() as d:
            return build_needle_jsonl(_D([bad, _row("good", query="ok")]), Path(d) / "o.jsonl")

    def test_bad_rows_are_dropped_with_a_reason_not_a_crash(self):
        cases = {
            "int query": (_row("a", query=5), "query must be text"),
            "none query": (_row("b", query=None), "query must be text"),
            "nameless tool": (_row("c", tools=[{}]), "non-empty text name"),
            "blank tool name": (_row("d", tools=[{"name": "  "}]), "non-empty text name"),
            "unserializable": (_row("e", tools=[{"name": "t", "o": object()}]), "serializable"),
            "lone surrogate": (_row("f", query="\ud800 x"), "serializable"),
            "nan in tool": (_row("g", tools=[{"name": "t", "w": float("nan")}]), "serializable"),
            "unhashable answer name": (_row("h", answers=[{"name": ["t"], "arguments": {}}]), "answer call name must be text"),
            "duplicate tool name": (_row("k", tools=[T, dict(T)]), "duplicate tool name"),
            "int reasoning": (_row("i", reasoning=5), "reasoning must be text"),
            "list system": (_row("j", system=["s"]), "system must be text"),
        }
        for label, (row, reason) in cases.items():
            m = self._build(row)
            self.assertEqual(m["rows"], 1, label)
            self.assertIn(reason, m["dropped_detail"][0]["reason"], label)


if __name__ == "__main__":
    unittest.main()
