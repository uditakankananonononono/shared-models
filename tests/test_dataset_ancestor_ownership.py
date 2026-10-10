"""SM-N4: root-owned system symlinks in the ancestor path are tolerated; every other symlink stays refused.

Synthetic temp trees. Root ownership is SIMULATED by patching Path.lstat's st_uid (no root and no macOS here).
"""
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from instinct_models.training.dataset import ExampleRow, build_needle_jsonl

ROWS = [ExampleRow(query="add task buy milk", tools=[{"name": "t"}], answers=[{"name": "t", "arguments": {"title": "buy milk"}}],
                   confirmed=True, source_ref="a", product="atlas"),
        ExampleRow(query="hello there", tools=[{"name": "t"}], answers=[], confirmed=True, source_ref="b", product="atlas")]


class DS:
    product = "atlas"

    def rows(self):
        return ROWS


def as_root(*owned):
    """Patch Path.lstat so the given symlink paths report st_uid 0; everything else is real."""
    real = Path.lstat
    owned = {str(p) for p in owned}

    def lstat(self, *a, **k):
        st = real(self, *a, **k)
        if str(self) in owned:
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, 0, st.st_gid, st.st_size,
                                   int(st.st_atime), int(st.st_mtime), int(st.st_ctime)))
        return st
    return patch.object(Path, "lstat", lstat)


class AncestorOwnership(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "private" / "var" / "folders").mkdir(parents=True)
        self.var = self.d / "var"  # stands in for /var -> /private/var
        os.symlink(self.d / "private" / "var", self.var)
        self.real_out = self.d / "private" / "var" / "folders" / "o"

    def test_root_owned_ancestor_symlink_is_tolerated_and_writes_into_the_real_tree(self):
        with as_root(self.var):
            m = build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")
        self.assertEqual(m["rows"], 2)
        self.assertTrue((self.real_out / "x.jsonl").is_file())
        self.assertTrue((self.real_out / "x.jsonl.manifest.json").is_file())

    def test_same_symlink_owned_by_the_user_is_still_refused(self):
        with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
            build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")
        self.assertFalse(self.real_out.exists())

    def test_root_owned_symlink_as_the_immediate_directory_is_still_refused(self):
        link = self.d / "outlink"
        os.symlink(self.d / "private", link)
        with as_root(link):
            with self.assertRaisesRegex(ValueError, "symlinked output directory"):
                build_needle_jsonl(DS(), link / "x.jsonl")

    def test_a_non_root_symlink_above_a_root_owned_one_is_still_refused(self):
        top = self.d / "top"
        os.symlink(self.d, top)  # user-owned link higher up: top/var is the root-owned one below it
        with as_root(self.d / "top" / "var", self.var):
            with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                build_needle_jsonl(DS(), top / "var" / "folders" / "o" / "x.jsonl")

    def test_non_posix_never_exempts(self):
        with as_root(self.var), patch("instinct_models.training.dataset._IS_POSIX", False):
            with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")


if __name__ == "__main__":
    unittest.main()
