import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from instinct_models.training.needle_lora import NeedleLoRAJob, train_needle_lora


def _runner_factory(on_build=None):
    def runner(cmd, env):
        Path(cmd[-1]).write_bytes(b"fixture")
        if cmd[1] == "build" and on_build:
            on_build()
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return runner


class RegistryRaceAndParentTests(unittest.TestCase):
    def test_output_dir_symlink_is_refused_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            real = d / "real"; real.mkdir()
            link = d / "link"; link.symlink_to(real)
            data = d / "data"; data.write_text("{}\n")
            calls = []
            def runner(cmd, env):
                calls.append(cmd); return subprocess.CompletedProcess(cmd, 0, "", "")
            with self.assertRaises(ValueError):
                train_needle_lora(NeedleLoRAJob("atlas", str(data), str(link)), runner=runner)
            self.assertEqual(calls, [])
            self.assertEqual(list(real.iterdir()), [])

    def test_o_nofollow_alone_blocks_a_symlink_swapped_in_during_the_run(self):
        # Both is_symlink checks are patched to False, so only O_NOFOLLOW at open() can stop the append.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            data = d / "data"; data.write_text("{}\n")
            out = d / "out"
            outside = d / "outside"; outside.write_bytes(b"private original\n")
            plant = lambda: (out / "registry.jsonl").symlink_to(outside)
            with patch.object(Path, "is_symlink", lambda self: False):
                with self.assertRaises(OSError):
                    train_needle_lora(NeedleLoRAJob("atlas", str(data), str(out)), runner=_runner_factory(plant))
            self.assertEqual(outside.read_bytes(), b"private original\n")


if __name__ == "__main__":
    unittest.main()
