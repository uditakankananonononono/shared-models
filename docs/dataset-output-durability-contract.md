# Dataset output durability contract (SM-PEER-1)

Base: `a215196a3eca7dd4e571f853a9d5c91ee9984f05` (`instinct_models/training/dataset.py`, `build_needle_jsonl`).
Companion tests: `tests/test_dataset_output_durability.py` (authored, not run).
Product changes: proposed only, in the separate `dataset-output-durability-proposed.patch` (NOT applied; peer judgment and independent audit gate).
Current-behavior statements below are READ from the base source, not executed.

## (a) Ancestor directory of the output path is a symlink

Current (read): only `out.parent.is_symlink()` is checked - the immediate parent. Any symlink higher in the path is silently traversed and the write lands in the linked-to tree.
Decision: FIX. New `_check_no_symlink_ancestors` refuses when the output directory or ANY of its ancestors is a symlink; the immediate-parent refusal message is unchanged so the existing contract and tests still match.
Reader view after crash between writes: no write is ever initiated through a symlinked ancestor, so a crash can only leave the ordinary two-file states of case (c) inside the real output tree, never files in the linked-to tree.
Remaining limits: check-then-open race (an attacker who can swap a directory for a symlink after the check still races; no dirfd-relative opens); paths under intentionally symlinked system roots (macOS `/var` -> `/private/var`) are refused - callers must pass a pre-resolved (`os.path.realpath`) path.

## (b) Planted temp name `.<file>.<pid>.tmp` is a DIRECTORY

Current (read): `_write_atomic` runs `tmp.unlink(missing_ok=True)`; on a planted directory that raises `IsADirectoryError` (or `PermissionError`) - an uncaught `OSError`, not the guard contract's `ValueError` - and the planted directory blocks the build.
Decision: FIX. Before unlinking, a non-symlink directory at the temp name is refused with `ValueError("temp path exists and is not a regular file: ...")`; directories are never removed. Planted symlinks and regular files keep base behavior (unlinked, never followed).
Reader view after crash between writes: the build fails before any rename, so after any crash readers see only the previously committed data/manifest pair.
Remaining limits: a same-pid planted directory still denies the run (availability, not integrity); other non-regular files (FIFO, socket) retain base unlink behavior.

## (c) Data replaced atomically, manifest write fails

Current (read): `_write_atomic(out)` succeeds, then `_write_atomic(manifest_path)` may fail, leaving new data with an old or missing manifest whose `sha256` no longer matches the data file. No rollback exists.
Decision: FIX (exception path). If the manifest write raises, the previous data bytes are restored with a second atomic write, or the new data file is removed when there was no previous file; the original exception is re-raised. Rollback is best-effort.
Reader view after crash between writes: a hard crash (power loss) between the two renames can still leave new data with an old or missing manifest - readers MUST treat a manifest whose `sha256` does not match the data file as invalid and rebuild.
Remaining limits: the crash-window mismatch is detectable via `sha256`, not prevented (no journal); if the rollback write itself fails, mixed state remains and the original error still propagates.

## (d) No fsync: replace is atomic, not crash-durable

Current (read): `os.replace` gives atomicity but no `fsync` of file or directory happens anywhere, so a crash can lose the rename or the contents.
Decision: FIX. `_write_atomic` flushes and fsyncs the temp file before the rename and fsyncs the containing directory after it (`os.name == "posix"` only).
Reader view after crash between writes: once a rename's directory fsync has returned, a reader after a crash sees the new file with complete contents; a crash before it yields the old pair, never a torn file at the target path.
Remaining limits: storage that lies about fsync (some drives, RAID caches, NFS) can still lose data; Windows directory fsync is unsupported and skipped; pair consistency across a crash remains per case (c).

## Compatibility

The success path is byte-identical to a215196a by reading: the JSONL text construction, the manifest dict keys/values, and `json.dumps(manifest, indent=2)` are unchanged, and fsync/rollback add no bytes. The fixed ROWS of `tests/test_dataset_output_guard.py` therefore produce the same data bytes and the same manifest keys and sha256. All eight existing output-guard tests remain valid UNMODIFIED; the immediate-parent symlink refusal message is preserved for `test_symlinked_output_directory_is_refused`.
