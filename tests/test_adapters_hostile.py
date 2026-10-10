"""SM-U-C-HOSTILE-ADAPTER-LOG assertions (authored by the peer, run and amended by the integrator)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from instinct_models.training.adapters_hostile import HardenedJsonlConfirmationLog
from instinct_models.training.dataset import build_needle_jsonl


TOOL = {"name": "add_task", "description": "add", "parameters": {
    "properties": {"title": {"type": "string"}}, "required": ["title"]}}


def record(**changes):
    value = {
        "id": "local-row",
        "query": "add task buy milk",
        "tools": [TOOL],
        "call": {"name": "add_task", "arguments": {"title": "buy milk"}},
        "owner_decision": "confirmed",
    }
    value.update(changes)
    return value


class HostileAdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "owner.jsonl"
        self.log = HardenedJsonlConfirmationLog("atlas", self.path)

    def write_records(self, *records):
        self.path.write_text("\n".join(json.dumps(item) for item in records) + "\n",
                             encoding="utf-8")

    def test_invalid_utf8_is_file_valueerror_before_any_row(self):
        good = (json.dumps(record()) + "\n").encode("utf-8")
        self.path.write_bytes(good + b"\xffPRIVATE-CONTENT\n")
        iterator = iter(self.log.rows())
        with self.assertRaises(ValueError) as caught:
            next(iterator)
        self.assertIs(type(caught.exception), ValueError)
        self.assertEqual(str(caught.exception), "confirmation log is not valid UTF-8")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(self.log.skipped, [])

    def test_utf8_is_explicit_and_locale_independent(self):
        self.write_records(record(query="add task café", call={
            "name": "add_task", "arguments": {"title": "café"}}))
        original = Path.read_text
        with patch.object(Path, "read_text", autospec=True, side_effect=original) as read:
            rows = list(self.log.rows())
        read.assert_called_once_with(self.path, encoding="utf-8-sig", errors="strict")
        self.assertEqual(rows[0].answers[0]["arguments"], {"title": "café"})

    BOM = b"\xef\xbb\xbf"

    def line(self, **changes):
        return (json.dumps(record(**changes)) + "\n").encode("utf-8")

    def test_leading_bom_does_not_drop_the_first_row(self):
        self.path.write_bytes(self.BOM + self.line(id="r1") + self.line(id="r2"))
        rows = list(self.log.rows())
        self.assertEqual([r.source_ref for r in rows], ["r1", "r2"])
        self.assertEqual(self.log.skipped, [])

    def test_file_without_bom_is_unchanged(self):
        self.path.write_bytes(self.line(id="r1") + self.line(id="r2"))
        self.assertEqual([r.source_ref for r in self.log.rows()], ["r1", "r2"])
        self.assertEqual(self.log.skipped, [])

    def test_bom_in_the_middle_of_the_file_is_still_skipped(self):
        self.path.write_bytes(self.line(id="r1") + self.BOM + self.line(id="r2") + self.line(id="r3"))
        rows = list(self.log.rows())
        self.assertEqual([r.source_ref for r in rows], ["r1", "r3"])
        self.assertEqual(self.log.skipped, [{"source_ref": "owner.jsonl:2", "reason": "unreadable row: JSONDecodeError"}])

    def test_bom_then_invalid_utf8_is_still_the_file_level_value_error(self):
        self.path.write_bytes(self.BOM + self.line(id="r1") + b"\xffPRIVATE-CONTENT\n")
        with self.assertRaises(ValueError) as caught:
            list(self.log.rows())
        self.assertNotIn("PRIVATE-CONTENT", str(caught.exception))

    def test_double_bom_strips_only_one(self):
        self.path.write_bytes(self.BOM + self.BOM + self.line(id="r1") + self.line(id="r2"))
        rows = list(self.log.rows())
        self.assertEqual([r.source_ref for r in rows], ["r2"])
        self.assertEqual(self.log.skipped, [{"source_ref": "owner.jsonl:1", "reason": "unreadable row: JSONDecodeError"}])

    def test_deep_json_is_skipped_and_next_row_survives(self):
        # Construct as text, not json.dumps, so test setup itself cannot recurse.
        depth = max(10000, sys.getrecursionlimit() * 2)
        deep = '{"tools":[],"query":"deep","call":null,"nested":' + '[' * depth + '0' + ']' * depth + '}'
        self.path.write_text(deep + "\n" + json.dumps(record()) + "\n", encoding="utf-8")
        rows = list(self.log.rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source_ref, "local-row")
        self.assertEqual(self.log.skipped, [{
            "source_ref": "owner.jsonl:1", "reason": "unreadable row: RecursionError"}])

    def test_parser_recursion_is_content_free_and_continues(self):
        self.path.write_text("hostile\nvalid\n", encoding="utf-8")
        with patch("instinct_models.training.adapters.json.loads",
                   side_effect=[RecursionError("PRIVATE-CONTENT"), record()]):
            rows = list(self.log.rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.log.skipped, [{
            "source_ref": "owner.jsonl:1", "reason": "unreadable row: RecursionError"}])
        self.assertNotIn("PRIVATE-CONTENT", str(self.log.skipped))

    def test_non_object_arguments_are_skipped_including_falsey_shapes(self):
        for arguments in (False, 0, "", [], ["buy milk"], "buy milk", 1):
            with self.subTest(arguments=arguments):
                self.write_records(record(call={"name": "add_task", "arguments": arguments}), record())
                rows = list(self.log.rows())
                self.assertEqual(len(rows), 1)
                self.assertEqual(self.log.skipped, [{
                    "source_ref": "owner.jsonl:1", "reason": "arguments must be an object"}])

    def test_explicit_null_arguments_mean_no_arguments_like_the_legacy_reader(self):
        self.write_records(record(call={"name": "add_task", "arguments": None}))
        self.assertEqual(list(self.log.rows())[0].answers, [{"name": "add_task", "arguments": {}}])
        self.assertEqual(self.log.skipped, [])

    def test_raw_unicode_line_separators_inside_a_row_do_not_split_it(self):
        for sep in ("\u2028", "\u0085", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e"):
            with self.subTest(sep=repr(sep)):
                r = record()
                r["query"] = "a" + sep + "b"
                self.path.write_text(json.dumps(r, ensure_ascii=False).replace("\\u2028", "\u2028") + "\n", encoding="utf-8")
                rows = list(self.log.rows())
                self.assertEqual(len(rows), 1)
                self.assertEqual(self.log.skipped, [])

    def test_default_reader_is_the_hardened_one(self):
        from instinct_models.training.adapters import JsonlConfirmationLog
        self.assertIs(JsonlConfirmationLog, HardenedJsonlConfirmationLog)

    def test_missing_arguments_and_object_arguments_are_preserved(self):
        self.write_records(record(call={"name": "add_task"}),
                           record(call={"name": "add_task", "arguments": {}}), record())
        rows = list(self.log.rows())
        self.assertEqual([row.answers[0]["arguments"] for row in rows],
                         [{}, {}, {"title": "buy milk"}])
        self.assertEqual(self.log.skipped, [])

    def test_non_list_tools_are_skipped(self):
        for tools in (None, False, 0, "", {}, TOOL, "add_task"):
            with self.subTest(tools=tools):
                self.write_records(record(tools=tools), record())
                self.assertEqual(len(list(self.log.rows())), 1)
                self.assertEqual(self.log.skipped, [{
                    "source_ref": "owner.jsonl:1", "reason": "tools must be a list"}])

    def test_non_object_call_is_skipped(self):
        for call in (False, 0, "", [], "add_task"):
            with self.subTest(call=call):
                self.write_records(record(call=call), record())
                self.assertEqual(len(list(self.log.rows())), 1)
                self.assertEqual(self.log.skipped[0]["reason"], "call must be an object or null")

    def test_off_topic_confirmation_privacy_and_reference_are_preserved(self):
        missing_call = record(id="", owner_decision="rejected", private=False)
        del missing_call["call"]
        self.write_records(record(call=None), missing_call)
        rows = list(self.log.rows())
        self.assertEqual([row.answers for row in rows], [[], []])
        self.assertEqual([row.confirmed for row in rows], [True, False])
        self.assertEqual([row.private for row in rows], [True, False])
        self.assertEqual(rows[1].source_ref, "owner.jsonl:2")

    def test_product_tags_survive_reader_and_foreign_rows_are_dropped(self):
        self.write_records(record(id="local"), record(id="foreign", product="meemee"))
        rows = list(self.log.rows())
        self.assertEqual([row.product for row in rows], ["atlas", "meemee"])
        out = Path(self.directory.name) / "training.jsonl"
        manifest = build_needle_jsonl(self.log, out)
        self.assertEqual(manifest["rows"], 1)
        self.assertEqual(manifest["dropped_detail"], [{
            "source_ref": "foreign", "reason": "row belongs to 'meemee', not 'atlas'"}])
        exported = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(exported, [{"query": "add task buy milk", "tools": [TOOL],
                                     "answers": [{"name": "add_task", "arguments": {"title": "buy milk"}}]}])

    def test_explicit_null_product_preserves_existing_builder_behavior(self):
        self.write_records(record(product=None))
        self.assertIsNone(list(self.log.rows())[0].product)
        manifest = build_needle_jsonl(self.log, Path(self.directory.name) / "training.jsonl")
        self.assertEqual(manifest["rows"], 1)
        self.assertEqual(manifest["dropped"], 0)

    def test_unconfirmed_rows_still_dropped_by_builder(self):
        self.write_records(record(), record(id="rejected", owner_decision="rejected"),
                           record(id="unreviewed", owner_decision="unreviewed"))
        manifest = build_needle_jsonl(self.log, Path(self.directory.name) / "training.jsonl")
        self.assertEqual(manifest["rows"], 1)
        self.assertEqual(manifest["dropped_detail"], [
            {"source_ref": "rejected", "reason": "not owner-confirmed"},
            {"source_ref": "unreviewed", "reason": "not owner-confirmed"}])

    def test_blank_lines_keep_physical_refs_and_malformed_rows_continue(self):
        self.path.write_text("\nnot json\n[]\n{}\n" + json.dumps(record()) + "\n", encoding="utf-8")
        self.assertEqual(len(list(self.log.rows())), 1)
        self.assertEqual(self.log.skipped, [
            {"source_ref": "owner.jsonl:2", "reason": "unreadable row: JSONDecodeError"},
            {"source_ref": "owner.jsonl:3", "reason": "unreadable row: ValueError"},
            {"source_ref": "owner.jsonl:4", "reason": "unreadable row: KeyError"}])

    def test_skipped_resets_on_repeat_iteration_and_file_failure(self):
        self.path.write_text("not json\n", encoding="utf-8")
        self.assertEqual(list(self.log.rows()), [])
        self.assertEqual(len(self.log.skipped), 1)
        self.write_records(record())
        self.assertEqual(len(list(self.log.rows())), 1)
        self.assertEqual(self.log.skipped, [])
        self.log.skipped.append({"source_ref": "old", "reason": "old"})
        self.path.write_bytes(b"\xff")
        with self.assertRaises(ValueError):
            list(self.log.rows())
        self.assertEqual(self.log.skipped, [])

    def test_filesystem_errors_remain_filesystem_errors(self):
        with self.assertRaises(FileNotFoundError):
            list(self.log.rows())

    def test_unknown_product_is_refused(self):
        with self.assertRaisesRegex(ValueError, "product must be"):
            HardenedJsonlConfirmationLog("other", self.path)
