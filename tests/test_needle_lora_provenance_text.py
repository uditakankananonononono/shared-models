"""Text-only checks on the PROPOSED needle_lora provenance patch (not applied). Nothing is imported from the
product or executed. Authored, not run."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = (ROOT / "proposals" / "sm-lora-provenance.patch").read_text()
DOC = (ROOT / "docs" / "needle-lora-provenance-contract.md").read_text()
ADDED = "\n".join(l[1:] for l in PATCH.splitlines() if l.startswith("+") and not l.startswith("+++"))
BASE = "dcfa10e8d1bf995d50b47391fbe7df41d212b79e"


class LoraProvenanceProposalTests(unittest.TestCase):
    def test_patch_touches_only_needle_lora(self):
        self.assertEqual([l for l in PATCH.splitlines() if l.startswith("+++ ")],
                         ["+++ b/instinct_models/training/needle_lora.py"])

    def test_dataset_hash_taken_once_before_training_and_recorded(self):
        self.assertIn("data_sha = _sha(data)", ADDED)
        self.assertIn('"dataset_sha256": data_sha', ADDED)

    def test_post_training_mismatch_refuses_registry_write(self):
        self.assertIn("dataset changed during training; registry not written", ADDED)

    def test_base_checkpoint_hash_new_field_and_before_side_effects(self):
        self.assertIn('"base_checkpoint_sha256": base_sha', ADDED)
        i, j = PATCH.index("base_sha = _base_checkpoint_sha"), PATCH.index("out = Path(job.out_dir)")
        self.assertLess(i, j)

    def test_none_only_when_not_provided_missing_is_error(self):
        self.assertIn("if path_str is None:\n        return None", ADDED)
        self.assertIn("base checkpoint not found", ADDED)
        self.assertIn("DEFAULT_BASE_CHECKPOINT", ADDED)
        self.assertIn("base_checkpoint: str | None = None", ADDED)
        self.assertIn("is not a regular file", ADDED)
        self.assertIn("is not readable", ADDED)

    def test_reader_and_heal_untouched(self):
        for name in ("read_registry", "RegistryTornError", "os.pread", "_refuse"):
            self.assertNotIn(name, ADDED)

    def test_doc_names_base_and_unproven(self):
        self.assertIn(BASE, DOC)
        self.assertIn("## UNPROVEN", DOC)


if __name__ == "__main__":
    unittest.main()
