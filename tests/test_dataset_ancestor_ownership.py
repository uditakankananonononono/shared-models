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


def simulate(owned=(), parent=None, parent_mode=None, parent_uid=0):
    """Patch Path.lstat. Paths in `owned` report st_uid 0. `parent` (a directory, or a list of them, holding the
    links) reports st_uid=parent_uid and, if parent_mode is given, that permission mode. Everything else is real."""
    real = Path.lstat
    owned = {str(p) for p in owned}
    parents = {str(p) for p in (parent if isinstance(parent, (list, tuple)) else [parent]) if p is not None}

    def lstat(self, *a, **k):
        st = real(self, *a, **k)
        uid, mode = st.st_uid, st.st_mode
        if str(self) in owned:
            uid = 0
        if str(self) in parents:
            uid = parent_uid
            if parent_mode is not None:
                mode = (mode & ~0o7777) | parent_mode
        return os.stat_result((mode, st.st_ino, st.st_dev, st.st_nlink, uid, st.st_gid, st.st_size,
                               int(st.st_atime), int(st.st_mtime), int(st.st_ctime)))
    return patch.object(Path, "lstat", lstat)


class AncestorOwnership(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "private" / "var" / "folders").mkdir(parents=True)
        self.var = self.d / "var"  # stands in for /var -> /private/var
        os.symlink(self.d / "private" / "var", self.var)
        self.real_out = self.d / "private" / "var" / "folders" / "o"

    def test_root_owned_ancestor_symlink_is_tolerated_and_writes_into_the_real_tree(self):
        with simulate([self.var], parent=self.d, parent_mode=0o755):
            m = build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")
        self.assertEqual(m["rows"], 2)
        self.assertTrue((self.real_out / "x.jsonl").is_file())
        self.assertTrue((self.real_out / "x.jsonl.manifest.json").is_file())

    def test_same_symlink_owned_by_the_user_is_still_refused(self):
        with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
            build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")
        self.assertFalse(self.real_out.exists())

    def test_user_owned_link_in_a_root_owned_parent_is_still_refused(self):
        with simulate([], parent=self.d, parent_mode=0o755):  # parent looks like a system dir; the link itself is the user's
            with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")
        self.assertFalse(self.real_out.exists())

    def test_root_owned_symlink_as_the_immediate_directory_is_still_refused(self):
        link = self.d / "outlink"
        os.symlink(self.d / "private", link)
        with simulate([link], parent=self.d, parent_mode=0o755):
            with self.assertRaisesRegex(ValueError, "symlinked output directory"):
                build_needle_jsonl(DS(), link / "x.jsonl")

    def test_a_non_root_symlink_above_a_root_owned_one_is_still_refused(self):
        x = self.d / "x"
        (x / "sub").mkdir(parents=True)
        os.symlink(self.real_out.parent, x / "sub" / "var")  # exempt link, in a real (simulated root) parent
        top = self.d / "top"
        os.symlink(x, top)  # user-owned link higher up, reached after the exempt one
        with simulate([top / "sub" / "var"], parent=top / "sub", parent_mode=0o755):
            with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                build_needle_jsonl(DS(), top / "sub" / "var" / "o" / "x.jsonl")

    def test_root_owned_link_in_a_group_or_other_writable_parent_is_refused(self):
        for mode in (0o775, 0o757, 0o777, 0o722):
            with self.subTest(mode=oct(mode)):
                with simulate([self.var], parent=self.d, parent_mode=mode):
                    with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                        build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")
        self.assertFalse(self.real_out.exists())

    def test_root_owned_link_in_a_non_root_owned_parent_is_refused(self):
        with simulate([self.var], parent=self.d, parent_mode=0o755, parent_uid=1234):
            with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")

    def test_exempt_link_whose_target_is_a_user_owned_symlink_is_refused(self):
        outside = self.d / "outside"
        (outside / "folders").mkdir(parents=True)
        hop = self.d / "hop"
        os.symlink(outside, hop)  # user-owned symlink: the target chain of the "system" link below
        sysl = self.d / "sys"
        os.symlink(hop, sysl)
        with simulate([sysl], parent=self.d, parent_mode=0o755):
            with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                build_needle_jsonl(DS(), sysl / "folders" / "o" / "x.jsonl")
        self.assertFalse((outside / "folders" / "o").exists())  # nothing written through the chain

    def test_exempt_link_to_a_real_user_writable_directory_is_accepted_documented_limit(self):
        # LIMIT, not a goal: the destination's own permissions are not inspected (macOS /tmp -> sticky world-writable
        # /private/tmp would otherwise break). This test documents it so a later change to it is deliberate.
        writable = self.d / "writable"
        writable.mkdir(mode=0o777)
        os.chmod(writable, 0o777)
        sysl = self.d / "sys2"
        os.symlink(writable, sysl)
        with simulate([sysl], parent=self.d, parent_mode=0o755):
            build_needle_jsonl(DS(), sysl / "o" / "x.jsonl")
        self.assertTrue((writable / "o" / "x.jsonl").is_file())

    def test_non_posix_never_exempts(self):
        with simulate([self.var], parent=self.d, parent_mode=0o755), patch("instinct_models.training.dataset._IS_POSIX", False):
            with self.assertRaisesRegex(ValueError, "symlinked ancestor"):
                build_needle_jsonl(DS(), self.var / "folders" / "o" / "x.jsonl")


if __name__ == "__main__":
    unittest.main()
