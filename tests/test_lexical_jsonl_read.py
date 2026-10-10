"""LexicalToolModel.from_jsonl reads what build_needle_jsonl writes. Synthetic temp files only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from instinct_models.lexical import LexicalToolModel
from instinct_models.training.dataset import ExampleRow, build_needle_jsonl

TOOL = {"name": "add_task", "description": "add a task"}


def row(query, **extra):
    return {"query": query, "tools": [TOOL], "answers": [{"name": "add_task", "arguments": {}}], **extra}


def raw_line(r):
    return json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n"


class FromJsonlRead(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "train.jsonl"

    def test_raw_line_separators_inside_rows_do_not_split_them(self):
        for sep in ("\u2028", "\u0085"):
            with self.subTest(sep=repr(sep)):
                self.path.write_bytes(raw_line(row(f"add task buy{sep}milk")) + raw_line(row("add task call mum")))
                self.assertEqual(LexicalToolModel.from_jsonl(self.path).trained_rows, 2)

    def test_producer_round_trip_with_raw_u2028(self):
        class DS:
            product = "atlas"

            def rows(self):
                return [ExampleRow(query="add task buy\u2028milk", tools=[TOOL],
                                   answers=[{"name": "add_task", "arguments": {}}], confirmed=True, source_ref="a", product="atlas"),
                        ExampleRow(query="hello there", tools=[TOOL], answers=[], confirmed=True, source_ref="b", product="atlas")]
        out = Path(self.dir.name) / "built.jsonl"
        manifest = build_needle_jsonl(DS(), out)
        self.assertIn("\u2028", out.read_text(encoding="utf-8"))  # the builder really wrote a raw separator
        self.assertEqual(LexicalToolModel.from_jsonl(out).trained_rows, manifest["rows"])

    def test_leading_bom_trains(self):
        self.path.write_bytes(b"\xef\xbb\xbf" + raw_line(row("add task buy milk")))
        self.assertEqual(LexicalToolModel.from_jsonl(self.path).trained_rows, 1)

    def test_invalid_utf8_is_a_clean_value_error(self):
        self.path.write_bytes(raw_line(row("add task buy milk")) + b"\xff\xfe\n")
        with self.assertRaises(ValueError) as caught:
            LexicalToolModel.from_jsonl(self.path)
        text = str(caught.exception)
        self.assertEqual(text, f"{self.path}: not valid UTF-8")
        self.assertNotIn("0x", text)
        self.assertNotIn("position", text)

    def test_mid_file_bom_is_still_a_line_error(self):
        self.path.write_bytes(raw_line(row("add task one")) + b"\xef\xbb\xbf" + raw_line(row("add task two")))
        with self.assertRaisesRegex(ValueError, "line 2 is not valid JSON"):
            LexicalToolModel.from_jsonl(self.path)

    def test_encoding_is_explicit_so_the_locale_cannot_matter(self):
        self.path.write_bytes(raw_line(row("add task caf\u00e9")))
        original = Path.read_text
        with patch.object(Path, "read_text", autospec=True, side_effect=original) as read:
            LexicalToolModel.from_jsonl(self.path)
        read.assert_called_once_with(self.path, encoding="utf-8-sig", errors="strict")


if __name__ == "__main__":
    unittest.main()
