"""SM-N5: registry reader + append-heal. Real temp files; no training."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

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

    def test_heal_on_bom_only_file_and_empty_file(self):
        self.reg.write_bytes(b"")
        train(self.out, self.data)
        self.assertFalse(self.reg.read_bytes().startswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
