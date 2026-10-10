"""Failure-injection tests for the dataset output durability contract.

Unit SM-PEER-1; see docs/dataset-output-durability-contract.md.

AUTHORED, NOT RUN (PREP-NORUN). These tests specify the FIXED behavior in the
separate proposed dataset.py patch. Against base a215196a, by reading:
 - test_symlinked_ancestor_directory_is_refused FAILS (base writes through the
   ancestor symlink; no refusal exists),
 - test_planted_directory_at_temp_name_is_refused ERRORs/FAILs (base unlink
   raises IsADirectoryError, not ValueError),
 - both manifest-failure rollback tests FAIL (base keeps the new data bytes),
 - test_file_and_directory_fsynced_around_each_rename FAILS (base never fsyncs).
No network, no services; real filesystem only under tempfile.mkdtemp().
"""
import os
import tempfile
import unittest
from pathlib import Path

from instinct_models.training.dataset import ExampleRow, build_needle_jsonl

ROWS = [ExampleRow(query="add task buy milk", tools=[{"name": "t"}], answers=[{"name": "t", "arguments": {"title": "buy milk"}}],
                   confirmed=True, source_ref="a", product="atlas"),
        ExampleRow(query="hello there", tools=[{"name": "t"}], answers=[], confirmed=True, source_ref="b", product="atlas")]
ROWS2 = [ExampleRow(query="add task buy bread", tools=[{"name": "t"}], answers=[{"name": "t", "arguments": {"title": "buy bread"}}],
                    confirmed=True, source_ref="c", product="atlas"),
         ExampleRow(query="hey there", tools=[{"name": "t"}], answers=[], confirmed=True, source_ref="d", product="atlas")]


class DS:
    product = "atlas"

    def rows(self):
        return ROWS


class DS2(DS):
    def rows(self):
        return ROWS2


class AncestorSymlink(unittest.TestCase):
    """Case (a)."""

    def test_symlinked_ancestor_directory_is_refused(self):
        # Mutation making this fail: deleting the ancestor `raise ValueError(...)`
        # line in _check_no_symlink_ancestors.
        d = Path(tempfile.mkdtemp())
        real = d / "real" / "sub"
        real.mkdir(parents=True)
        os.symlink(d / "real", d / "link")
        with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
            build_needle_jsonl(DS(), d / "link" / "sub" / "x.jsonl")
        self.assertEqual(list(real.iterdir()), [])  # nothing written through the link


class TempNameDirectory(unittest.TestCase):
    """Case (b)."""

    def test_planted_directory_at_temp_name_is_refused_with_value_error(self):
        # Mutation making this fail: deleting the
        # `if os.path.lexists(tmp) and not tmp.is_symlink() and stat.S_ISDIR(...)` guard.
        d = Path(tempfile.mkdtemp())
        (d / "o").mkdir()
        tmp = d / "o" / f".x.jsonl.{os.getpid()}.tmp"
        tmp.mkdir()
        with self.assertRaises(ValueError) as ctx:
            build_needle_jsonl(DS(), d / "o/x.jsonl")
        self.assertIn("temp path", str(ctx.exception))
        self.assertTrue(tmp.is_dir())  # the planted directory is refused, never removed
        self.assertFalse((d / "o/x.jsonl").exists())


class ManifestFailureRollback(unittest.TestCase):
    """Case (c): os.replace patched to raise on the SECOND call (manifest)."""

    def _fail_second_replace(self):
        orig = os.replace
        calls = []

        def boom_second(a, b):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("manifest write failed")
            return orig(a, b)

        return orig, boom_second

    def test_manifest_write_failure_rolls_back_data(self):
        # Mutation making this fail: deleting the rollback restore block in
        # build_needle_jsonl's `except BaseException:` handler.
        d = Path(tempfile.mkdtemp())
        build_needle_jsonl(DS(), d / "o/x.jsonl")
        old_data = (d / "o/x.jsonl").read_bytes()
        old_manifest = (d / "o/x.jsonl.manifest.json").read_bytes()
        orig, boom_second = self._fail_second_replace()
        os.replace = boom_second
        try:
            with self.assertRaises(OSError):
                build_needle_jsonl(DS2(), d / "o/x.jsonl")  # different rows -> different bytes
        finally:
            os.replace = orig
        self.assertEqual((d / "o/x.jsonl").read_bytes(), old_data)  # base FAILS: new bytes remain
        self.assertEqual((d / "o/x.jsonl.manifest.json").read_bytes(), old_manifest)
        self.assertEqual([p.name for p in (d / "o").iterdir() if p.name.endswith(".tmp")], [])

    def test_manifest_write_failure_on_first_build_leaves_no_data(self):
        # Mutation making this fail: deleting the `out.unlink(missing_ok=True)`
        # restore line in the rollback block.
        d = Path(tempfile.mkdtemp())
        orig, boom_second = self._fail_second_replace()
        os.replace = boom_second
        try:
            with self.assertRaises(OSError):
                build_needle_jsonl(DS(), d / "o/x.jsonl")
        finally:
            os.replace = orig
        self.assertFalse((d / "o/x.jsonl").exists())  # base FAILS: data remains with no manifest
        self.assertFalse((d / "o/x.jsonl.manifest.json").exists())
        self.assertEqual([p.name for p in d.iterdir() if p.name.endswith(".tmp")], [])


class CrashDurability(unittest.TestCase):
    """Case (d): fsync ordering is the contract."""

    def test_file_and_directory_fsynced_around_each_rename(self):
        # Mutation making this fail: deleting the `os.fsync(f.fileno())` line in
        # _write_atomic (order check breaks) or the `_fsync_dir(path.parent)` line
        # (one fsync short).
        d = Path(tempfile.mkdtemp())
        events = []
        orig_fsync, orig_replace = os.fsync, os.replace
        os.fsync = lambda fd: events.append("fsync")

        def rec_replace(a, b):
            events.append("replace")
            return orig_replace(a, b)

        os.replace = rec_replace
        try:
            build_needle_jsonl(DS(), d / "o/x.jsonl")
        finally:
            os.fsync, os.replace = orig_fsync, orig_replace
        # per output file: file fsync BEFORE the rename, directory fsync AFTER it
        self.assertEqual(events, ["fsync", "replace", "fsync", "fsync", "replace", "fsync"])


if __name__ == "__main__":
    unittest.main()
