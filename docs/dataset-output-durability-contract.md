# Dataset output durability contract (SM-PEER-1, revision 2)

Base: `a215196a3eca7dd4e571f853a9d5c91ee9984f05` (`instinct_models/training/dataset.py`, `build_needle_jsonl`).
Revision 2 incorporates the peer audit of `ff52e52fa58dfc3d26741a3a1ccd2b3f34c85666`.
Companion tests: `tests/test_dataset_output_durability.py` (authored, not run).
Product changes: proposed only, in the separate `dataset-output-durability-proposed.patch` (NOT applied; peer judgment and independent audit gate).
Current-behavior statements below are READ from the base source, not executed.

## (a) Ancestor directory of the output path is a symlink

Current (read): only `out.parent.is_symlink()` is checked - the immediate parent. Any symlink higher in the path is silently traversed and the write lands in the linked-to tree.
Decision: FIX. New `_check_no_symlink_ancestors` refuses when the output directory or ANY of its ancestors is a symlink; the immediate-parent refusal message is unchanged so the existing contract and tests still match.
Reader view after crash between writes: no write is ever initiated through a symlinked ancestor, so any post-crash state is confined to the real output tree, where the pair states of case (c) apply.
Remaining limits: the refusal is LEXICAL-ONLY with a check/open race - an attacker who can swap a directory for a symlink between the check and the open still races (no dirfd-relative opens); paths under intentionally symlinked system roots (macOS `/var` -> `/private/var`) are refused unless the caller passes a pre-resolved (`os.path.realpath`) path.

## (b) Planted temp name `.<file>.<pid>.tmp` is a DIRECTORY

Current (read): `_write_atomic` runs `tmp.unlink(missing_ok=True)`; on a planted directory that raises `IsADirectoryError` (or `PermissionError`) - an uncaught `OSError`, not the guard contract's `ValueError` - and the planted directory blocks the build.
Decision: FIX. Before unlinking, a non-symlink directory at the temp name is refused with `ValueError("temp path exists and is not a regular file: ...")`; directories are never removed. Planted symlinks and regular files keep base behavior (unlinked, never followed).
Reader view after crash between writes: the build fails before any rename, so after any crash readers see only the previously committed data/manifest pair.
Remaining limits: the guard itself is a check-then-unlink sequence, so a swap between the check and the unlink still races; a read-only planted file at the temp name still raises an uncaught `PermissionError` (OSError, not ValueError); a same-pid planted directory denies the run (availability, not integrity); other non-regular files (FIFO, socket) retain base unlink behavior.

## (c) Data replaced atomically, manifest write fails

Current (read): `_write_atomic(out)` succeeds, then `_write_atomic(manifest_path)` may fail at any phase, leaving new data with an old or missing manifest whose `sha256` no longer matches the data file. No rollback exists.
Decision: FIX (exception path, phase-aware). The manifest write can fail BEFORE its rename (old manifest untouched) or AFTER it (e.g. the manifest's directory fsync raised - the new manifest is already committed). Rollback therefore restores BOTH files to their pre-build generations: prior data and prior manifest bytes are read before any write; on manifest-write failure the data file is restored (or removed on a first build) and the manifest is likewise restored or removed, whatever phase failed. Prior bytes are restored RAW - they need not be UTF-8 - and cleanup failures are swallowed so the ORIGINAL exception always propagates.
Reader view after crash between writes: a crash between the data rename and the manifest rename, or during rollback, can leave any pairing of old/new data with old/new/missing manifest - readers MUST treat a manifest whose `sha256` does not match the data file as invalid and rebuild (detectable, never crash-proven).
Remaining limits: rollback is NOT crash-durable and no such claim is made - the rollback rename/unlink is not followed by a directory fsync, and directories created by `mkdir(parents=True)` are never fsynced, so a crash can resurrect the pre-rollback state; the pair mismatch after a crash is detectable via `sha256`, not prevented (no journal).

## (d) No fsync: replace is atomic, not crash-durable

Current (read): `os.replace` gives atomicity but no `fsync` of file or directory happens anywhere.
Decision: FIX, scoped precisely. `_write_atomic` flushes and fsyncs the temp file before that file's rename and fsyncs the containing directory after that file's rename (`os.name == "posix"` only).
Reader view after crash between writes: the claim is PER-FILE fsync ordering ONLY - each file's contents are written out before its rename and its directory is fsynced after - but whether a rename survives a crash landing between that rename and its directory fsync is platform-dependent, so after a crash a reader may see either generation of either file and must validate the manifest `sha256` (pair mismatch detectable, not prevented; NO crash proof is offered).
Remaining limits: storage that lies about fsync (some drives, RAID caches, NFS) can still lose data; Windows directory fsync is unsupported and skipped (the test asserting fsync ordering is gated on `os.name == "posix"`); pair consistency across a crash remains per case (c).

## Compatibility

The success path is byte-identical to a215196a by reading: the JSONL text construction, the manifest dict keys/values, and `json.dumps(manifest, indent=2)` are unchanged, and the revised `_write_atomic` writes `str` payloads as UTF-8 with no newline translation (identical bytes to the previous text-mode write); fsync and rollback add no bytes. The fixed ROWS of `tests/test_dataset_output_guard.py` therefore produce the same data bytes and the same manifest keys and sha256. All eight existing output-guard tests remain valid UNMODIFIED; the immediate-parent symlink refusal message is preserved for `test_symlinked_output_directory_is_refused`.
