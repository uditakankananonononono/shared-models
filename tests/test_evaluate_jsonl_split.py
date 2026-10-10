"""JSONL line-split contract tests for training/evaluate.py _load_rows.

Candidate unit: evaluate.py line 14 splitlines handling; base
a4da7e5f34eaf30aadc69fc7360d06159e9c4763 (pinned at authoring). See
docs/evaluate-jsonl-line-split-contract.md.

AUTHORED, NOT RUN (PREP-NORUN). These tests specify the FIXED behavior in the
separate proposed patch (splitlines() -> split("\\n")). Against base a4da7e5f,
by reading, the special-character and line-number tests FAIL: splitlines cuts a
raw U+2028/U+2029/U+0085 inside a valid JSON string in two, and _load_rows
fails fast on the head fragment ("line 1: not valid JSON") instead of ever
reaching the real row. The CRLF, CR-only and trailing/blank-line tests PASS at
base too and guard the fix against regression; for those inputs the two
splitters give equivalent ROW RESULTS, not identical element sequences:
split("\\n") yields a final empty element after a trailing newline, which the
blank-line guard skips. Product change is proposed only, NOT applied.
No network, no services; real filesystem only under tempfile.
"""
import json
import tempfile
import unittest
from pathlib import Path

from instinct_models.training.evaluate import _load_rows

TOOL = {"name": "add_task", "description": "add", "parameters": {"properties": {"title": {"type": "string"}}, "required": ["title"]}}


def row(query, answers=None):
    return {"query": query, "tools": [TOOL],
            "answers": answers if answers is not None else [{"name": "add_task", "arguments": {"title": "x"}}]}


def write(d, text):
    p = Path(d) / "rows.jsonl"
    p.write_text(text, encoding="utf-8")
    return p


class RawBoundaryCharacters(unittest.TestCase):
    """U+0085 / U+2028 / U+2029 may sit RAW inside a valid JSON string; a JSONL
    parser must not treat them as line boundaries."""

    def test_row_with_literal_u2028_in_query_parses(self):
        # Mutation making this fail: changing `text.split("\n")` back to `splitlines()`.
        with tempfile.TemporaryDirectory() as d:
            p = write(d, json.dumps(row("add task buy \u2028 milk"), ensure_ascii=False) + "\n")
            rows = _load_rows(p)  # base FAILS: splitlines cuts the row -> "line 1: not valid JSON"
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query"], "add task buy \u2028 milk")

    def test_row_with_literal_u2029_and_u0085_parse(self):
        # Mutation making this fail: changing `text.split("\n")` back to `splitlines()`.
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(row("add task one\u2029two"), ensure_ascii=False) + "\n"
                    + json.dumps(row("add task three\u0085four"), ensure_ascii=False) + "\n")
            p = write(d, text)
            rows = _load_rows(p)  # base FAILS on both rows
        self.assertEqual([r["query"] for r in rows], ["add task one\u2029two", "add task three\u0085four"])

    def test_line_number_stays_true_after_a_special_character_row(self):
        # Mutation making this fail: changing `text.split("\n")` back to `splitlines()`
        # (base splits row 1 and fails fast on the head fragment, never reaching
        # the genuinely invalid row 2).
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(row("add task buy \u2028 milk"), ensure_ascii=False) + "\n"
                    + "not json\n")
            p = write(d, text)
            with self.assertRaisesRegex(ValueError, "line 2: not valid JSON"):
                _load_rows(p)  # base FAILS: raises "line 1" for the split fragment instead


class LineEndingCompatibility(unittest.TestCase):
    def test_crlf_file_still_parses(self):
        # Mutation making this fail: splitting ONLY on "\r\n" (drops lone-\n files)
        # or any change that stops tolerating the trailing \r.
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(row("add task buy milk")) + "\r\n"
                    + json.dumps({"query": "off topic chat", "tools": [TOOL], "answers": []}) + "\r\n")
            p = write(d, text)
            rows = _load_rows(p)  # expected PASS at base as well: guards the fix against CRLF regression
        self.assertEqual(len(rows), 2)

    def test_cr_only_file_still_parses(self):
        # Path.read_text universal-newlines mode translates lone \r to \n before
        # either splitter sees the text, so a CR-only file still parses.
        # Mutation making this fail: changing `text.split("\n")` to `split("\r")`.
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(row("add task buy milk")) + "\r"
                    + json.dumps({"query": "off topic chat", "tools": [TOOL], "answers": []}) + "\r")
            p = write(d, text)
            rows = _load_rows(p)  # expected PASS at base as well (splitlines also splits on \r); peer executes
        self.assertEqual(len(rows), 2)

    def test_trailing_newline_and_blank_lines_behave_as_before(self):
        # Mutation making this fail: dropping the `if not line.strip(): continue` guard.
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(row("add task buy milk")) + "\n\n"
                    + json.dumps({"query": "off topic chat", "tools": [TOOL], "answers": []}) + "\n")
            p = write(d, text)
            rows = _load_rows(p)  # expected PASS at base as well: guards trailing/blank-line behavior
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
