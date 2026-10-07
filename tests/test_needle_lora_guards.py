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
