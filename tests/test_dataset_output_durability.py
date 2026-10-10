"""Failure-injection tests for the dataset output durability contract.

Unit SM-PEER-1 revision 3 (second peer audit incorporated); see
docs/dataset-output-durability-contract.md.

AUTHORED, NOT RUN (PREP-NORUN). These tests specify the FIXED behavior in the
separate proposed dataset.py patch, except where noted. Against base a215196a,
by reading, ALL tests in this file FAIL (no ancestor refusal, no temp-directory
guard, no rollback, no fsync, unguarded temp cleanup).

Against earlier proposals of THIS unit, by reading:
 - The ff52e52 proposal fails only the two revision-2 probes:
   test_manifest_dir_fsync_failure_restores_both_files (it restored only the
   data file) and test_rollback_restores_non_utf8_prior_bytes_and_preserves_original_error
   (it decoded prior bytes as UTF-8, masking the original error). The ancestor
   and tempdir tests PASS there.
 - The 66824c7 (revision-2) proposal additionally fails the three revision-3
   probes: test_temp_cleanup_failure_never_masks_the_primary_write_error
   (unguarded cleanup masks the primary error),
   test_data_phase_failure_after_rename_also_rolls_back (data write outside the
   rollback try), and test_rollback_attempts_both_restorations_independently
   (one shared try, second restore skipped).
 - test_planted_directory_at_temp_name_is_refused_with_value_error is the
   behavior SPEC for the peer's consolidated SM-N1 guard: it FAILS under this
   unit's own proposal (guard withdrawn per the SM-N1 overlap) until the
   consolidated guard lands.

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


def fail_second_replace():
    orig = os.replace
    calls = []

    def boom_second(a, b):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("manifest write failed")
        return orig(a, b)

    return orig, boom_second


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
    """Case (b) - SUPERSEDED by the peer's SM-N1 consolidation: this test is the
    behavior spec for the consolidated temp-directory guard (this unit's own
    proposal deliberately carries no guard, to avoid duplicating SM-N1)."""

    def test_planted_directory_at_temp_name_is_refused_with_value_error(self):
        # Mutation making this fail: deleting the directory guard in the
        # consolidated (SM-N1) _write_atomic.
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
    """Case (c): failures at the manifest rename phase."""

    def test_manifest_write_failure_rolls_back_data(self):
        # Mutation making this fail: deleting the data-restore half of the
        # rollback block in build_needle_jsonl.
        d = Path(tempfile.mkdtemp())
        build_needle_jsonl(DS(), d / "o/x.jsonl")
        old_data = (d / "o/x.jsonl").read_bytes()
        old_manifest = (d / "o/x.jsonl.manifest.json").read_bytes()
        orig, boom_second = fail_second_replace()
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
        orig, boom_second = fail_second_replace()
        os.replace = boom_second
        try:
            with self.assertRaises(OSError):
                build_needle_jsonl(DS(), d / "o/x.jsonl")
        finally:
            os.replace = orig
        self.assertFalse((d / "o/x.jsonl").exists())  # base FAILS: data remains with no manifest
        self.assertFalse((d / "o/x.jsonl.manifest.json").exists())
        self.assertEqual([p.name for p in d.iterdir() if p.name.endswith(".tmp")], [])

    def test_rollback_restores_non_utf8_prior_bytes_and_preserves_original_error(self):
        # Mutation making this fail: changing the rollback restore to
        # `_write_atomic(out, old_data.decode("utf-8"))` - raises UnicodeDecodeError,
        # masking the original OSError.
        d = Path(tempfile.mkdtemp())
        (d / "o").mkdir()
        old_data = b"\xff\xfe\x00 binary prior content"
        old_manifest = b"old manifest bytes \xff"
        (d / "o/x.jsonl").write_bytes(old_data)
        (d / "o/x.jsonl.manifest.json").write_bytes(old_manifest)
        orig, boom_second = fail_second_replace()
        os.replace = boom_second
        try:
            with self.assertRaises(OSError) as ctx:
                build_needle_jsonl(DS(), d / "o/x.jsonl")
        finally:
            os.replace = orig
        self.assertIn("manifest write failed", str(ctx.exception))  # not masked by UnicodeDecodeError
        self.assertEqual((d / "o/x.jsonl").read_bytes(), old_data)  # raw bytes restored verbatim
        self.assertEqual((d / "o/x.jsonl.manifest.json").read_bytes(), old_manifest)

    def test_rollback_attempts_both_restorations_independently(self):
        # Mutation making this fail: wrapping both restorations in ONE shared try
        # so the first failure skips the second.
        d = Path(tempfile.mkdtemp())
        build_needle_jsonl(DS(), d / "o/x.jsonl")
        old_data = (d / "o/x.jsonl").read_bytes()
        old_manifest = (d / "o/x.jsonl.manifest.json").read_bytes()
        orig = os.replace
        calls = []

        def boom(a, b):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("manifest write failed")  # primary error
            if len(calls) == 3:
                raise OSError("data restore denied")  # first rollback restore fails
            return orig(a, b)  # second rollback restore must still be attempted

        os.replace = boom
        try:
            with self.assertRaises(OSError) as ctx:
                build_needle_jsonl(DS2(), d / "o/x.jsonl")
        finally:
            os.replace = orig
        self.assertIn("manifest write failed", str(ctx.exception))  # primary error preserved
        self.assertEqual((d / "o/x.jsonl.manifest.json").read_bytes(), old_manifest)  # still restored
        self.assertNotEqual((d / "o/x.jsonl").read_bytes(), old_data)  # failed restore: documented mixed state


class WriteCleanup(unittest.TestCase):
    """_write_atomic: cleanup must never mask the primary write error."""

    def test_temp_cleanup_failure_never_masks_the_primary_write_error(self):
        # Mutation making this fail: deleting the inner `except OSError: pass`
        # guard around the cleanup `tmp.unlink(missing_ok=True)` in _write_atomic.
        d = Path(tempfile.mkdtemp())
        orig_replace, orig_unlink = os.replace, os.unlink
        os.replace = lambda a, b: (_ for _ in ()).throw(OSError("primary write failure"))

        def flaky_unlink(p, *a, **k):
            if str(p).endswith(".tmp") and os.path.lexists(p):
                raise PermissionError("cleanup denied")  # secondary error during cleanup
            return orig_unlink(p, *a, **k)

        os.unlink = flaky_unlink
        try:
            with self.assertRaises(OSError) as ctx:
                build_needle_jsonl(DS(), d / "o/x.jsonl")
        finally:
            os.replace, os.unlink = orig_replace, orig_unlink
        self.assertEqual(str(ctx.exception), "primary write failure")
        self.assertNotIsInstance(ctx.exception, PermissionError)


class DirFsyncPhaseFailures(unittest.TestCase):
    """Case (c) phase-awareness for the directory-fsync phase (POSIX only: that
    phase exists only where _write_atomic fsyncs the directory)."""

    @unittest.skipUnless(os.name == "posix", "directory fsync phase is POSIX-only")
    def test_manifest_dir_fsync_failure_restores_both_files(self):
        # Mutation making this fail: deleting the manifest-restore half of the
        # rollback block (the `else: _write_atomic(manifest_path, old_manifest)` arm).
        d = Path(tempfile.mkdtemp())
        build_needle_jsonl(DS(), d / "o/x.jsonl")
        old_data = (d / "o/x.jsonl").read_bytes()
        old_manifest = (d / "o/x.jsonl.manifest.json").read_bytes()
        orig_fsync = os.fsync
        calls = []

        def fsync_boom(fd):
            calls.append(fd)
            if len(calls) == 4:  # data fsync+dir fsync, manifest file fsync, manifest replace done; its dir fsync fails
                raise OSError("directory fsync failed")
            return orig_fsync(fd)

        os.fsync = fsync_boom
        try:
            with self.assertRaises(OSError) as ctx:
                build_needle_jsonl(DS2(), d / "o/x.jsonl")
        finally:
            os.fsync = orig_fsync
        self.assertIn("directory fsync failed", str(ctx.exception))
        self.assertEqual((d / "o/x.jsonl").read_bytes(), old_data)  # rolled back
        self.assertEqual((d / "o/x.jsonl.manifest.json").read_bytes(), old_manifest)  # restored, not left new
        self.assertEqual([p.name for p in (d / "o").iterdir() if p.name.endswith(".tmp")], [])

    @unittest.skipUnless(os.name == "posix", "directory fsync phase is POSIX-only")
    def test_data_phase_failure_after_rename_also_rolls_back(self):
        # Mutation making this fail: moving `_write_atomic(out, text)` back OUTSIDE
        # the rollback try in build_needle_jsonl.
        d = Path(tempfile.mkdtemp())
        build_needle_jsonl(DS(), d / "o/x.jsonl")
        old_data = (d / "o/x.jsonl").read_bytes()
        old_manifest = (d / "o/x.jsonl.manifest.json").read_bytes()
        orig_fsync = os.fsync
        calls = []

        def fsync_boom(fd):
            calls.append(fd)
            if len(calls) == 2:  # data file fsync done, data rename done; the data directory fsync fails
                raise OSError("directory fsync failed")
            return orig_fsync(fd)

        os.fsync = fsync_boom
        try:
            with self.assertRaises(OSError) as ctx:
                build_needle_jsonl(DS2(), d / "o/x.jsonl")
        finally:
            os.fsync = orig_fsync
        self.assertIn("directory fsync failed", str(ctx.exception))
        self.assertEqual((d / "o/x.jsonl").read_bytes(), old_data)  # no new-data/old-manifest mismatch
        self.assertEqual((d / "o/x.jsonl.manifest.json").read_bytes(), old_manifest)


class CrashDurability(unittest.TestCase):
    """Case (d): per-file fsync ordering is the contract; no pair crash proof.
    Runs on every platform with platform-adjusted expected events."""

    def test_file_and_directory_fsynced_around_each_rename(self):
        # Mutation making this fail: deleting the `os.fsync(f.fileno())` line in
        # _write_atomic (order check breaks) or the `_fsync_dir(path.parent)` line
        # (one fsync short on POSIX).
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
        # per output file: file fsync BEFORE its rename; directory fsync AFTER it (POSIX only)
        per_file = ["fsync", "replace"] + (["fsync"] if os.name == "posix" else [])
        self.assertEqual(events, per_file * 2)


if __name__ == "__main__":
    unittest.main()
