"""Behavior tests for proposals/sm-lora-provenance.patch (injected runner, no needle CLI, no network).
Authored, NOT run. They pass only AFTER the proposal is applied, so they live outside tests/ discovery."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from instinct_models.training.needle_lora import NeedleLoRAJob, read_registry, train_needle_lora

ROW = '{"query":"q","tools":[],"answers":[]}\n'


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def runner_writing(on_build=None):
    def run(cmd, env):
        Path(cmd[cmd.index("--out") + 1]).write_bytes(b"fixture")
        if cmd[1] == "build" and on_build:
            on_build()
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.data = self.d / "data.jsonl"
        self.data.write_text(ROW)
        self.out = self.d / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def job(self, **kw):
        return NeedleLoRAJob("atlas", str(self.data), str(self.out), **kw)

    def test_unprovided_checkpoint_records_none_keeps_default_argv_and_old_fields(self):
        calls = []
        def run(cmd, env):
            calls.append(cmd)
            return runner_writing()(cmd, env)
        rec = train_needle_lora(self.job(), runner=run)
        self.assertIsNone(rec["base_checkpoint_sha256"])
        self.assertEqual(calls[1][2], "checkpoints/needle2.pkl")
        for k in ("product", "dataset_sha256", "dataset_rows", "train_locally_only", "adapter", "tuned_weights",
                  "tuned_sha256", "epochs", "trained_at", "logs"):
            self.assertIn(k, rec)
        self.assertEqual(rec["dataset_sha256"], sha(ROW.encode()))

    def test_explicit_none_is_unprovided_and_records_none(self):
        calls = []
        def run(cmd, env):
            calls.append(cmd)
            return runner_writing()(cmd, env)
        rec = train_needle_lora(self.job(base_checkpoint=None), runner=run)
        self.assertIsNone(rec["base_checkpoint_sha256"])
        self.assertEqual(calls[1][2], "checkpoints/needle2.pkl")

    def test_provided_but_missing_checkpoint_is_an_error_before_any_step(self):
        calls = []
        with self.assertRaisesRegex(ValueError, "base checkpoint not found: absent.pkl"):
            train_needle_lora(self.job(base_checkpoint=str(self.d / "absent.pkl")), runner=lambda c, e: calls.append(c))
        self.assertEqual(calls, [])
        self.assertFalse(self.out.exists())

    def test_explicit_default_string_now_requires_the_file(self):
        old = os.getcwd()
        os.chdir(self.d)  # temp dir has no checkpoints/needle2.pkl
        try:
            with self.assertRaisesRegex(ValueError, "base checkpoint not found: needle2.pkl"):
                train_needle_lora(self.job(base_checkpoint="checkpoints/needle2.pkl"), runner=runner_writing())
        finally:
            os.chdir(old)
        self.assertFalse(self.out.exists())

    def test_empty_and_option_like_values_still_refused(self):
        for bad in ("", "--upload"):
            with self.assertRaises(ValueError, msg=bad):
                train_needle_lora(self.job(base_checkpoint=bad), runner=runner_writing())

    def test_existing_regular_checkpoint_is_hashed(self):
        ck = self.d / "base.pkl"
        ck.write_bytes(b"checkpoint bytes")
        rec = train_needle_lora(self.job(base_checkpoint=str(ck)), runner=runner_writing())
        self.assertEqual(rec["base_checkpoint_sha256"], sha(b"checkpoint bytes"))
        self.assertEqual(read_registry(self.out)[-1]["base_checkpoint_sha256"], sha(b"checkpoint bytes"))

    def test_missing_parent_directory_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "base checkpoint not found: base.pkl"):
            train_needle_lora(self.job(base_checkpoint=str(self.d / "nope" / "base.pkl")), runner=runner_writing())

    def test_directory_checkpoint_is_a_clear_error_before_any_step(self):
        (self.d / "ckdir").mkdir()
        calls = []
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            train_needle_lora(self.job(base_checkpoint=str(self.d / "ckdir")), runner=lambda c, e: calls.append(c))
        self.assertEqual(calls, [])
        self.assertFalse(self.out.exists())

    @unittest.skipIf(not hasattr(os, "geteuid") or os.geteuid() == 0, "needs a non-root POSIX user")
    def test_unreadable_checkpoint_is_a_clear_error(self):
        ck = self.d / "base.pkl"
        ck.write_bytes(b"x")
        ck.chmod(0)
        try:
            with self.assertRaisesRegex(ValueError, "not readable"):
                train_needle_lora(self.job(base_checkpoint=str(ck)), runner=runner_writing())
        finally:
            ck.chmod(0o600)

    def test_dataset_changed_during_training_refuses_registry_write(self):
        run = runner_writing(on_build=lambda: self.data.write_text(ROW + ROW))
        with self.assertRaisesRegex(ValueError, "changed during training"):
            train_needle_lora(self.job(), runner=run)
        self.assertFalse((self.out / "registry.jsonl").exists())

    def test_dataset_removed_during_training_refuses_registry_write(self):
        run = runner_writing(on_build=lambda: self.data.unlink())
        with self.assertRaisesRegex(ValueError, "changed during training"):
            train_needle_lora(self.job(), runner=run)
        self.assertFalse((self.out / "registry.jsonl").exists())

    def test_manifest_mismatch_still_refuses_before_training(self):
        Path(str(self.data) + ".manifest.json").write_text(json.dumps({"sha256": "0" * 64, "rows": 1}))
        calls = []
        with self.assertRaisesRegex(ValueError, "changed since its manifest"):
            train_needle_lora(self.job(), runner=lambda c, e: calls.append(c))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
