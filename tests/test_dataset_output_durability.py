"""Failure-injection tests for the dataset output durability contract.

Unit SM-PEER-1 revision 4 (third peer audit incorporated; prep stack rebased
onto base 50e4c1b = N1 temp-directory guard + N2 BOM fix landed). See
docs/dataset-output-durability-contract.md.

AUTHORED, NOT RUN (PREP-NORUN). These tests specify the FIXED behavior in the
separate COMBINED proposal patch (against 50e4c1b, retaining N1's guard).

Base-failure accounting:
- The peer's EXECUTED result on revision 3 against base a215196a was 8 FAIL /
  2 PASS (the peer's run, not this unit's - this unit executes nothing). The two
  passes were vacuous probes: test_temp_cleanup_failure_never_masks_the_primary_write_error
  (it raised on the DATA write with no prior output) and
  test_rollback_attempts_both_restorations_independently (the manifest never
  became NEW, so old-manifest equality was vacuous). Both are STRENGTHENED here
  on the peer's direction: the cleanup probe calls _write_atomic DIRECTLY; the
  independent-restoration probe makes the manifest NEW before the primary
  failure (POSIX directory-fsync phase), denies the FIRST (data) restore, and
  asserts the SECOND (manifest) restore actually runs and succeeds with the
  original error preserved.
- Against the current base 50e4c1b, by reading: 9 FAIL / 1 PASS -
  test_planted_directory_at_temp_name_is_refused_with_value_error now PASSES
  because the consolidated N1 guard has landed (it raises ValueError
  "output temp path is a directory"); it stays as the regression spec for that
  guard. Every other test still FAILS at 50e4c1b (no ancestor refusal, no
  rollback, no fsync, unguarded except-cleanup).

Against earlier proposals of THIS unit, by reading (scope-corrected):
- The ff52e52 (revision-1) proposal, counting only the R1/R2 tests that existed
  in that unit: fails the two revision-2 probes
  (test_manifest_dir_fsync_failure_restores_both_files,
  test_rollback_restores_non_utf8_prior_bytes_and_preserves_original_error);
  the ancestor and tempdir tests PASS there. The three revision-3 probes did
  not exist in that unit and are not counted against it.
- The 66824c7 (revision-2) proposal additionally fails the three revision-3
  probes (cleanup masking, data-phase rollback, shared-try restorations).
- The bada4a9 (revision-3) proposal fails the strengthened versions of the two
  probes above (its cleanup guard is in _write_atomic but the probe now calls
  _write_atomic directly - that one it PASSES; its restorations are independent
  but the strengthened probe also requires the manifest to have become NEW,
  which its rollback restores - see the per-test reading in the report).

No network, no services; real filesystem only under tempfile.mkdtemp().
"""
import os
import tempfile
import unittest
from pathlib import Path

from instinct_models.training.dataset import ExampleRow, build_needle_jsonl, _write_atomic

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
    """Case (b) - consolidated guard LANDED as N1 (base 50e4c1b): this test is
    now the regression spec for N1's guard (this unit's proposal carries no
    guard of its own)."""

    def test_planted_directory_at_temp_name_is_refused_with_value_error(self):
        # Mutation making this fail: deleting the S_ISDIR guard in the landed
        # N1 _write_atomic.
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


class WriteCleanup(unittest.TestCase):
    """_write_atomic: cleanup must never mask the primary write error."""

    def test_temp_cleanup_failure_never_masks_the_primary_write_error(self):
        # Mutation making this fail: deleting the inner `except OSError: pass`
        # guard around the cleanup `tmp.unlink(missing_ok=True)` in _write_atomic.
        # Strengthened (peer audit): calls _write_atomic DIRECTLY, so the probe
        # does not depend on build-level state and cannot pass vacuously.
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
                _write_atomic(d / "x.jsonl", "payload")
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

    @unittest.skipUnless(os.name == "posix", "the injected directory-fsync phase is POSIX-only")
    def test_rollback_attempts_both_restorations_independently(self):
        # Mutation making this fail: wrapping both restorations in ONE shared try
        # so the first failure skips the second.
        # Strengthened (peer audit): the manifest is NEW (its rename completed)
        # before the primary failure, the FIRST (data) restore is denied, and the
        # SECOND (manifest) restore must actually run and succeed - old-manifest
        # equality alone would be vacuous without the new-manifest phase.
        d = Path(tempfile.mkdtemp())
        build_needle_jsonl(DS(), d / "o/x.jsonl")
        old_data = (d / "o/x.jsonl").read_bytes()
        old_manifest = (d / "o/x.jsonl.manifest.json").read_bytes()
        orig_fsync, orig_replace = os.fsync, os.replace
        fsync_calls, replace_calls = [], []

        def fsync_boom(fd):
            fsync_calls.append(fd)
            if len(fsync_calls) == 4:  # manifest rename already done (manifest NEW); its directory fsync fails (primary)
                raise OSError("directory fsync failed")
            return orig_fsync(fd)

        def replace_partial(a, b):
            replace_calls.append(1)
            if len(replace_calls) == 3:  # deny the FIRST rollback restore (data)
                raise OSError("data restore denied")
            return orig_replace(a, b)

        os.fsync, os.replace = fsync_boom, replace_partial
        try:
            with self.assertRaises(OSError) as ctx:
                build_needle_jsonl(DS2(), d / "o/x.jsonl")
        finally:
            os.fsync, os.replace = orig_fsync, orig_replace
        self.assertIn("directory fsync failed", str(ctx.exception))  # ORIGINAL error preserved, not the secondary
        self.assertEqual((d / "o/x.jsonl.manifest.json").read_bytes(), old_manifest)  # NEW manifest restored: second restore RAN
        self.assertNotEqual((d / "o/x.jsonl").read_bytes(), old_data)  # first restore denied: documented mixed state
        self.assertEqual([p.name for p in (d / "o").iterdir() if p.name.endswith(".tmp")], [])


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
