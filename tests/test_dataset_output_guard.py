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

    def test_stale_or_planted_temp_name_does_not_block_or_get_followed(self):
        (self.d / "o").mkdir()
        tmp = self.d / "o" / f".x.jsonl.{os.getpid()}.tmp"
        tmp.write_text("stale")
        self.build()  # stale same-pid temp is removed, not a FileExistsError
        os.symlink(self.victim, tmp)
        self.build()  # planted symlink at the temp name is removed, never written through
        self.assertFalse(self.victim.exists())
        self.assertEqual([p.name for p in (self.d / "o").iterdir() if p.name.endswith(".tmp")], [])

    def temp_name(self):
        return self.d / "o" / f".x.jsonl.{os.getpid()}.tmp"

    def test_planted_directory_at_temp_name_is_a_value_error_and_left_alone(self):
        (self.d / "o").mkdir()
        self.temp_name().mkdir()
        with self.assertRaisesRegex(ValueError, "directory") as cm:
            self.build()
        self.assertNotIn(str(self.d), str(cm.exception))  # name only, no path or errno text
        self.assertTrue(self.temp_name().is_dir())
        self.assertEqual(sorted(p.name for p in (self.d / "o").iterdir()), [self.temp_name().name])  # no data, no manifest

    def test_planted_directory_with_content_is_left_intact(self):
        (self.d / "o").mkdir()
        self.temp_name().mkdir()
        (self.temp_name() / "keep").write_text("x")
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual((self.temp_name() / "keep").read_text(), "x")

    def test_symlink_to_a_directory_at_temp_name_is_unlinked_not_followed(self):
        (self.d / "o").mkdir()
        target = self.d / "elsewhere"
        target.mkdir()
        (target / "keep").write_text("x")
        os.symlink(target, self.temp_name())
        self.build()
        self.assertEqual((target / "keep").read_text(), "x")
        self.assertFalse(self.temp_name().exists() or self.temp_name().is_symlink())

    def test_unlink_failure_at_temp_name_is_a_value_error_without_detail(self):
        from unittest import mock
        (self.d / "o").mkdir()
        self.temp_name().write_text("stale")
        with mock.patch.object(Path, "unlink", side_effect=PermissionError(13, "secret detail")):
            with self.assertRaises(ValueError) as cm:
                self.build()
        self.assertEqual(str(cm.exception), f"cannot clear output temp path: {self.temp_name().name}")  # exact name-only text (never a numeric substring: the pid in the name may contain digits)
        self.assertNotIn("Errno", str(cm.exception))
        self.assertNotIn("secret detail", str(cm.exception))

    def test_valid_write_is_byte_identical_to_the_pre_change_output(self):
        self.build()
        self.assertEqual(hashlib.sha256((self.d / "o/x.jsonl").read_bytes()).hexdigest(),
                         "5ecbb3f6473cea8a6fea7b1f8af66cd600640ccb1f0822b9cd6893ab8f44e038")
        expected = ('{\n  "product": "atlas",\n  "rows": 2,\n  "dropped": 0,\n  "dropped_detail": [],\n'
                    '  "off_topic_ratio": 0.5,\n  "sha256": "5ecbb3f6473cea8a6fea7b1f8af66cd600640ccb1f0822b9cd6893ab8f44e038",\n'
                    '  "train_locally_only": true,\n  "path": ' + __import__("json").dumps(str(self.d / "o/x.jsonl")) +
                    ',\n  "warnings": []\n}')  # exact manifest text as written before this change (the path varies per run)
        self.assertEqual((self.d / "o/x.jsonl.manifest.json").read_text(), expected)

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
