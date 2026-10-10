# Needle LoRA registry provenance (proposal contract)
Status: authored, not run. The product change is the separate UNAPPLIED `proposals/sm-lora-provenance.patch`.
Base: shared-models `dcfa10e8d1bf995d50b47391fbe7df41d212b79e` (current peer main; 0d37dfc0, 90b7da68 (a40bc4f8, b0659776) and 555a8ce5 (6ab04994) LoRA packages are SUPERSEDED historical receipts). Content-overlap check (READ: `git diff --name-status 555a8ce5 dcfa10e8` = one added docs file; earlier ranges = adapters.py, router.py and their docs/tests/receipts): no overlap with needle_lora.py. Not touched: `read_registry`, the append-heal, the registry open/refusal code.

## Source facts (READ at the base, instinct_models/training/needle_lora.py)
- Docstring lines 6-8 say the registry records dataset hash, command and output hash "so a product can pin exactly what it serves".
- The dataset is hashed before training only for the manifest comparison (`_sha(data)` at line 121) and hashed AGAIN after training for the record (line 147). A dataset edited during a run is recorded as if it had been trained on.
- `job.base_checkpoint` (default `checkpoints/needle2.pkl`, line 36) is only passed to `needle build` (line 137); its content is not hashed or recorded, though the tuned weights depend on it.
- Existing tests never pass a base checkpoint (READ by grep: only tests/test_training_input_validation.py:54 passes `--upload` and the empty string, expecting ValueError), so they keep the default.

## Proposed behavior
1. Hash the dataset once before any training; that value is `dataset_sha256`. The manifest comparison reuses it.
2. After `needle build`, hash again. If it differs (or the file vanished or cannot be read), raise `ValueError("dataset changed during training; registry not written")`; no registry line is written.
3. `NeedleLoRAJob.base_checkpoint` becomes `str | None = None` (option A, as relayed by main at 13:18 IST from the peer). `None` means not provided: the `needle build` argv still uses the new constant `DEFAULT_BASE_CHECKPOINT = "checkpoints/needle2.pkl"` and `base_checkpoint_sha256` is `None`. ANY explicit non-None value, INCLUDING the default string, must be an existing, regular, readable, inspectable file (symlinks followed); otherwise a name-only `ValueError` is raised before the output dir is created or any step runs or the registry is written. Missing, directory, non-regular and unreadable are all errors; a missing path never becomes `None`. The empty-string and option-like (`--upload`) refusals are kept.
4. All existing record fields and their order are kept; the new key follows `tuned_sha256`.

**Semantic change to disclose:** a caller who explicitly passes `"checkpoints/needle2.pkl"` now needs that file to exist. Previously an absent file passed silently. Callers who pass nothing are unaffected.

## Out of scope / limits
- The base checkpoint is hashed once before training; it is not re-hashed after `needle build`, so a change during the (short) build step would not be detected.
- The check-then-open on the base checkpoint is not race-free (a FIFO swapped in after `stat` could block `open`).
- Large files are hashed in 1 MiB chunks; the dataset keeps the existing whole-file `_sha`.
- Nothing here validates that the checkpoint is a real Needle checkpoint.
- Does not touch reader, heal, fd handling or parent-swap behavior.

## UNPROVEN
Nothing was run: the patch was only parsed (`ast.parse`) and checked with `git apply --check` on scratch copies. The behavior test `proposals/tests/test_needle_lora_provenance.py` was authored, not executed, and only passes once the patch is applied.

## Mutant coverage (authored mapping, NOT run; peer-found mutants)
| Mutant | Test that should fail it (proposals/tests/test_needle_lora_provenance.py) |
|---|---|
| explicit None treated as an error or mapped to a hash | test_explicit_none_is_unprovided_and_records_none |
| default ignored (argv no longer carries DEFAULT_BASE_CHECKPOINT) | test_unprovided_checkpoint_records_none_keeps_default_argv_and_old_fields |
| None refused | same two tests (job with no or None checkpoint must run) |
| regular-file check removed | test_directory_checkpoint_is_a_clear_error_before_any_step |
| unreadable case removed | test_unreadable_checkpoint_is_a_clear_error (skipped for root) |
| None post-hash removed (dataset deleted during training) | test_dataset_removed_during_training_refuses_registry_write |
