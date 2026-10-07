import unittest
from instinct_models.training.dataset import ExampleRow, check_row

T = [{"name": "t"}]


def row(args):
    call = {"name": "t"} if args is ... else {"name": "t", "arguments": args}
    return ExampleRow("do x", T, [call], True, "ref")


class RowArgumentShapeTests(unittest.TestCase):
    def test_non_object_arguments_are_rejected(self):
        for bad in ("x", ["x"], 5):
            self.assertIsNotNone(check_row(row(bad)), bad)

    def test_missing_or_object_arguments_pass(self):
        self.assertIsNone(check_row(row(...)))
        self.assertIsNone(check_row(row({"a": "x"})))


class EmptyArgumentTests(unittest.TestCase):
    def test_blank_argument_value_is_rejected(self):
        for v in ("", "   "):
            self.assertIsNotNone(check_row(row({"a": v})), repr(v))


class DuplicateRowTests(unittest.TestCase):
    def test_identical_rows_are_deduplicated_with_reason(self):
        import tempfile
        from instinct_models.training.dataset import build_needle_jsonl

        class D:
            product = "atlas"

            def rows(self):
                for i in range(3):
                    yield ExampleRow("do x", T, [{"name": "t", "arguments": {"a": "x"}}], True, f"r{i}", private=False)
                yield ExampleRow("hello", T, [], True, "o", private=False)

        m = build_needle_jsonl(D(), tempfile.mkdtemp() + "/o.jsonl")
        self.assertEqual(m["rows"], 2)
        self.assertEqual(m["dropped"], 2)
        self.assertTrue(all("duplicate" in d["reason"] for d in m["dropped_detail"]))
