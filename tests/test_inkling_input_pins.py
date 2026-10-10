"""Text-only checks for SM-PEER-2. They read the evidence doc and the PROPOSED patch file (which is not applied).
Nothing here runs a script, build, pull or network call. Authored, not run."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "docs" / "inkling-input-pins-evidence.md").read_text()
PATCH = (ROOT / "proposals" / "sm-peer-2-serving-script-pins.patch").read_text()
ADDED = "\n".join(l[1:] for l in PATCH.splitlines() if l.startswith("+") and not l.startswith("+++"))
REMOVED = "\n".join(l[1:] for l in PATCH.splitlines() if l.startswith("-") and not l.startswith("---"))
NVFP4 = "b6a99534467840620d411e4cd4ad5819b2610d9c"
GGUF = "1a19ef82883cb7b9c581b93c30ea252dabbf658d"


class InputPinEvidenceTests(unittest.TestCase):
    def test_doc_lists_both_commit_shas(self):
        self.assertIn(NVFP4, DOC)
        self.assertIn(GGUF, DOC)

    def test_doc_states_hf_flag_has_no_revision_syntax(self):
        self.assertIn("`-hf` has no revision syntax", DOC)

    def test_doc_cites_file_and_line_for_mechanisms(self):
        for cite in ("arg_utils.py:946-949", "arg.cpp:3073-3081", "hf-cache.cpp:243", "download.cpp:67-75"):
            self.assertIn(cite, DOC)

    def test_doc_gguf_oids_are_64_hex_per_row(self):
        rows = [l for l in DOC.splitlines() if l.startswith("| UD-Q2_K_XL/")]
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertRegex(r, r"`[0-9a-f]{64}`")

    def test_doc_has_unproven_section(self):
        self.assertIn("## 5. UNPROVEN", DOC)


class ProposedPatchTests(unittest.TestCase):
    def test_vllm_pins_all_three_revisions_to_commit_var(self):
        for flag in ("--revision", "--code-revision", "--tokenizer-revision"):
            self.assertIn(flag + ' "$MODEL_REV"', ADDED)
        self.assertIn(NVFP4, ADDED)

    def test_vllm_rev_must_be_40_hex(self):
        self.assertIn("^[0-9a-f]{40}$", ADDED)

    def test_vllm_image_line_untouched(self):
        self.assertNotIn("VLLM_IMAGE=", ADDED + REMOVED)

    def test_llamacpp_existing_pin_untouched(self):
        self.assertNotIn("PIN_SHA=", ADDED + REMOVED)

    def test_llamacpp_dirty_tree_check_present(self):
        self.assertIn("git status --porcelain", ADDED)
        self.assertIn("is dirty", ADDED)

    def test_llamacpp_build_stamp_holds_pin_sha(self):
        self.assertIn("WANT_STAMP=\"$PIN_SHA", ADDED)
        self.assertIn("inkling-build-stamp", ADDED)

    def test_llamacpp_weights_commit_pinned_and_checked(self):
        self.assertIn('MODEL_REV="%s"' % GGUF, ADDED)
        self.assertIn('[ "$CUR" = "$MODEL_REV" ]', ADDED)

    def test_llamacpp_shards_have_sha256(self):
        self.assertGreaterEqual(len(re.findall(r"[0-9a-f]{64}  Inkling-Small-UD-", ADDED)), 12)

    def test_shard_manifest_is_an_array_not_a_printf_format_string(self):
        self.assertIn("SHARDS=()", ADDED)
        self.assertIn('printf \'%s\\n\' "${SHARDS[@]}"', ADDED)
        self.assertNotIn('printf "$SHARDS', ADDED)

    def test_no_silent_fallback_added(self):
        self.assertNotIn("|| " + "true", ADDED)


if __name__ == "__main__":
    unittest.main()
