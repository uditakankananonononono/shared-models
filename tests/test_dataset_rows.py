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
