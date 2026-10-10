"""SM-N5: registry reader + append-heal. Real temp files; no training."""
import json
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from instinct_models.training.needle_lora import NeedleLoRAJob, RegistryTornError, read_registry, train_needle_lora


def train(out, data):
    def runner(cmd, env):
        Path(cmd[-1]).write_bytes(b"fixture")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return train_needle_lora(NeedleLoRAJob("atlas", str(data), str(out)), runner=runner)


class RegistryReader(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)
        self.out = self.d / "out"
        self.out.mkdir()
        self.reg = self.out / "registry.jsonl"
        self.data = self.d / "data"
        self.data.write_text("{}\n")

    def tearDown(self):
        self._t.cleanup()

    def test_missing_registry_is_empty(self):
        self.assertEqual(read_registry(self.out), [])

    def test_round_trip_two_runs(self):
        a, b = train(self.out, self.data), train(self.out, self.data)
        self.assertEqual(read_registry(self.out), [a, b])

    def test_bom_on_first_record(self):
        self.reg.write_bytes(b"\xef\xbb\xbf" + b'{"product":"a"}\n{"product":"b"}\n')
        self.assertEqual([r["product"] for r in read_registry(self.out)], ["a", "b"])

    def test_u2028_inside_string_is_not_a_boundary(self):
        rec = {"product": "a", "note": "x\u2028y\x0bz\x85w"}
        self.reg.write_bytes((json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"))
        self.assertEqual(read_registry(self.out), [rec])

    def test_corrupt_middle_line_names_file_and_line(self):
        self.reg.write_text('{"a":1}\n{not json\n{"a":3}\n')
        with self.assertRaises(ValueError) as cm:
            read_registry(self.out)
        self.assertNotIsInstance(cm.exception, RegistryTornError)
        self.assertIn(str(self.reg), str(cm.exception))
        self.assertIn("line 2", str(cm.exception))

    def test_torn_final_line_is_flagged_distinctly(self):
        self.reg.write_text('{"a":1}\n{"a":2,"b":')
        with self.assertRaises(RegistryTornError) as cm:
            read_registry(self.out)
        self.assertIn("line 2", str(cm.exception))

    def test_unterminated_but_valid_final_line_is_a_record(self):
        self.reg.write_text('{"a":1}\n{"a":2}')
        self.assertEqual(read_registry(self.out), [{"a": 1}, {"a": 2}])

    def test_non_object_and_bad_utf8_refused(self):
        self.reg.write_text("[1]\n{}\n")
        with self.assertRaisesRegex(ValueError, "line 1"):
            read_registry(self.out)
        self.reg.write_bytes(b'{"a":"\xff"}\n')
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            read_registry(self.out)

    def test_symlinked_registry_refused(self):
        outside = self.d / "outside"
        outside.write_text("{}\n")
        self.reg.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "registry"):
            read_registry(self.out)

    def test_append_heals_missing_final_lf(self):
        self.reg.write_bytes(b'{"old":1}')  # hand-edited / interrupted: no final newline
        new = train(self.out, self.data)
        self.assertEqual(self.reg.read_bytes().count(b"\n"), 2)
        self.assertEqual(read_registry(self.out), [{"old": 1}, new])

    def test_append_does_not_add_blank_line_on_clean_file(self):
        a = train(self.out, self.data)
        b = train(self.out, self.data)
        self.assertEqual(self.reg.read_bytes(), (json.dumps(a) + "\n" + json.dumps(b) + "\n").encode())

    def test_heal_on_empty_file(self):
        self.reg.write_bytes(b"")
        new = train(self.out, self.data)
        self.assertFalse(self.reg.read_bytes().startswith(b"\n"))
        self.assertEqual(read_registry(self.out), [new])

    def test_heal_on_bom_only_file(self):
        self.reg.write_bytes(b"\xef\xbb\xbf")  # BOM, no content, no LF
        new = train(self.out, self.data)
        self.assertEqual(self.reg.read_bytes(), b"\xef\xbb\xbf\n" + (json.dumps(new) + "\n").encode())
        self.assertEqual(read_registry(self.out), [new])

    def test_valid_json_wrong_shape_on_final_unterminated_line_is_not_torn(self):
        for body in ('{"a":1}\n[1]', '{"a":1}\n"x"', '{"a":1}\n3'):
            self.reg.write_text(body)
            with self.assertRaises(ValueError) as cm:
                read_registry(self.out)
            self.assertNotIsInstance(cm.exception, RegistryTornError, body)
            self.assertIn("line 2", str(cm.exception))

    def test_late_symlink_swap_is_not_followed(self):
        outside = self.d / "outside"
        outside.write_text('{"secret":1}\n')
        self.reg.write_text('{"a":1}\n')
        real_open = os.open

        def swap_then_open(path, *a, **k):
            if str(path) == str(self.reg):  # the swap lands after any path-based pre-check
                self.reg.unlink()
                self.reg.symlink_to(outside)
            return real_open(path, *a, **k)
        with mock.patch("instinct_models.training.needle_lora.os.open", swap_then_open):
            with self.assertRaisesRegex(ValueError, "registry"):
                read_registry(self.out)

    def test_late_fifo_swap_refuses_without_hanging(self):
        if not hasattr(os, "mkfifo") or not hasattr(signal, "alarm"):
            self.skipTest("POSIX FIFO only")
        self.reg.write_text('{"a":1}\n')
        real_open = os.open

        def swap_then_open(path, *a, **k):
            if str(path) == str(self.reg):
                self.reg.unlink()
                os.mkfifo(self.reg)
            return real_open(path, *a, **k)

        def boom(*_):
            raise AssertionError("reader blocked on a FIFO")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(3)
        try:
            with mock.patch("instinct_models.training.needle_lora.os.open", swap_then_open):
                with self.assertRaisesRegex(ValueError, "regular"):
                    read_registry(self.out)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    def test_directory_registry_refused(self):
        self.reg.mkdir()
        with self.assertRaises(ValueError):
            read_registry(self.out)


if __name__ == "__main__":
    unittest.main()
