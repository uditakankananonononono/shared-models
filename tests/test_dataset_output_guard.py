import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path

from instinct_models.training.dataset import ExampleRow, build_needle_jsonl

ROWS = [ExampleRow(query="add task buy milk", tools=[{"name": "t"}], answers=[{"name": "t", "arguments": {"title": "buy milk"}}],
                   confirmed=True, source_ref="a", product="atlas"),
        ExampleRow(query="hello there", tools=[{"name": "t"}], answers=[], confirmed=True, source_ref="b", product="atlas")]


class DS:
    product = "atlas"

    def rows(self):
        return ROWS


class OutputGuard(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.victim = self.d / "victim"

    def build(self, rel="o/x.jsonl"):
        return build_needle_jsonl(DS(), self.d / rel)

    def test_valid_write_is_unchanged_and_manifest_matches(self):
        m = self.build()
        data = (self.d / "o/x.jsonl").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), m["sha256"])
        self.assertEqual(data.count(b"\n"), 2)
        self.assertTrue((self.d / "o/x.jsonl.manifest.json").is_file())
        self.assertEqual([p.name for p in (self.d / "o").iterdir() if p.name.endswith(".tmp")], [])
        self.build()  # overwriting a regular file is still allowed

    def test_symlinked_data_file_is_refused_and_target_untouched(self):
        (self.d / "o").mkdir()
        os.symlink(self.victim, self.d / "o/x.jsonl")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.build()
        self.assertFalse(self.victim.exists())

    def test_symlinked_manifest_is_refused_before_any_write(self):
        (self.d / "o").mkdir()
        os.symlink(self.victim, self.d / "o/x.jsonl.manifest.json")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.build()
        self.assertFalse(self.victim.exists())
        self.assertFalse((self.d / "o/x.jsonl").exists())  # nothing half-written

    def test_symlinked_output_directory_is_refused(self):
        (self.d / "real").mkdir()
        os.symlink(self.d / "real", self.d / "o")
        with self.assertRaisesRegex(ValueError, "symlinked output directory"):
            self.build()
        self.assertEqual(list((self.d / "real").iterdir()), [])

    def test_file_in_the_directory_path_is_a_value_error(self):
        (self.d / "f").write_text("x")
        with self.assertRaises(ValueError):
            self.build("f/sub/x.jsonl")

    def test_existing_non_regular_target_is_refused(self):
        (self.d / "o/x.jsonl").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            self.build()

    def test_failed_write_leaves_no_temp_and_keeps_old_file(self):
        self.build()
        good = (self.d / "o/x.jsonl").read_bytes()
        orig = os.replace

        def boom(a, b):
            raise OSError("disk")

        os.replace = boom
        try:
            with self.assertRaises(OSError):
                self.build()
        finally:
            os.replace = orig
        self.assertEqual((self.d / "o/x.jsonl").read_bytes(), good)
        self.assertEqual([p.name for p in (self.d / "o").iterdir() if p.name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
