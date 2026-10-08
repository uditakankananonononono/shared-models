import subprocess
import tempfile
import unittest
from pathlib import Path

from instinct_models.training.needle_lora import NeedleLoRAJob, train_needle_lora


def ok(cmd, env):
    return subprocess.CompletedProcess(cmd, 0, "", "")


class LoRAGuardTests(unittest.TestCase):
    def _job(self, d, product="atlas"):
        data = Path(d) / "data.jsonl"
        data.write_text('{"query":"q","tools":[],"answers":[]}\n')
        return NeedleLoRAJob(product, str(data), str(Path(d) / "out"))

    def test_product_name_cannot_escape_out_dir(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ("../evil", "a/b", ""):
                with self.assertRaises(ValueError):
                    train_needle_lora(self._job(d, bad), runner=ok)
            self.assertFalse((Path(d) / "evil-adapter.pkl").exists())

    def test_stale_tuned_file_does_not_count_as_build_success(self):
        with tempfile.TemporaryDirectory() as d:
            job = self._job(d)
            out = Path(job.out_dir); out.mkdir()
            (out / "atlas-tuned.cact").write_bytes(b"stale")
            with self.assertRaises(RuntimeError):
                train_needle_lora(job, runner=ok)


class ManifestClaimTests(unittest.TestCase):
    def test_refuses_when_dataset_changed_after_manifest(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            job = LoRAGuardTests()._job(d)
            Path(job.dataset_jsonl + ".manifest.json").write_text(json.dumps({"sha256": "0" * 64, "rows": 1}))
            with self.assertRaises(ValueError):
                train_needle_lora(job, runner=ok)

    def test_never_passes_upload_or_hf_repo(self):
        import os
        seen = []

        def runner(cmd, env):
            seen.append((cmd, env))
            out = Path(cmd[-1])
            out.write_bytes(b"x")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        os.environ["NEEDLE_HF_REPO"] = "someone/repo"
        try:
            with tempfile.TemporaryDirectory() as d:
                train_needle_lora(LoRAGuardTests()._job(d), runner=runner)
        finally:
            del os.environ["NEEDLE_HF_REPO"]
        for cmd, env in seen:
            self.assertNotIn("--upload", cmd)
            self.assertNotIn("NEEDLE_HF_REPO", env)
