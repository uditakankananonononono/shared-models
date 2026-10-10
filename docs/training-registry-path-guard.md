# Training registry path guard

Needle training refuses a pre-existing registry.jsonl symlink/nonregular file
before removing stale outputs or invoking the CLI. Append uses O_NOFOLLOW when
available and validates the opened regular fd. Real filesystem test preserves
external target bytes and zero runner calls; normal append remains supported.
The injected runner writes deterministic artifact bytes, not trained weights.
No actual Needle training, inference, upload or model acceptance is asserted.

Not output-directory containment: operator selects out_dir; hostile parent
replacement races remain. Windows lacks O_NOFOLLOW, no race-safe claim there.
Training effects can precede a late append error; no retry/rollback added.
Concurrent registry serialization/durability are not solved.

Append also uses O_NONBLOCK where available: a late-substituted FIFO refuses
rather than waiting for a reader. Real POSIX FIFO runner substitution test uses
a two-second subprocess deadline. This is leaf-only, not parent-race containment.

## Reading and appending (SM-N5)

`read_registry(out_dir)` returns the records of `registry.jsonl`, oldest first (missing file = empty list). Lines split
on LF only, so U+2028/U+0085 inside a JSON string are not boundaries. One UTF-8 BOM at the start is ignored. A corrupt
line followed by more data raises ValueError naming the file and line number. A final line with no LF whose JSON is
incomplete or malformed raises `RegistryTornError` (a ValueError subclass): it is reported, never returned as a record. A
missing LF is consistent with an interrupted append but does not prove a crash. Valid JSON of the wrong shape (e.g. `[1]`)
is an ordinary ValueError, not torn. A final line
with no LF that does parse is returned. The reader opens the leaf with O_RDONLY|O_NOFOLLOW|O_NONBLOCK, checks the open descriptor is a regular file, and reads
from that descriptor, so a symlink or FIFO swapped in after a path check is refused rather than followed (leaf only; a
hostile parent replacement race is not covered, as for the writer). It does not check
that the files a record names still exist or match `tuned_sha256`; callers compare that themselves.

Append now heals a missing final LF: if the file is non-empty and its last byte is not LF, one LF is written before the
new record, so two records cannot fuse on one line. Our own writes always end in LF, so a clean file is byte-for-byte
unchanged. Not solved: the torn partial line itself stays in the file (the heal terminates it, so the reader then reports
it as a corrupt line at that position); the append is not fsynced or atomic across crashes; concurrent appenders are not
serialized; the last-byte check and the write are not one atomic step. The registry fd is now opened read-write
(O_RDWR|O_APPEND) so the last byte can be read.

Platform and behavior notes: the reader and writer rely on POSIX facts (`os.pread`, `O_NOFOLLOW`, `O_NONBLOCK`); on Windows
O_NOFOLLOW/O_NONBLOCK are absent so the symlink/FIFO protection does not apply and `os.pread` is unavailable, so the append
heal is POSIX-only and untested there. Opening the registry O_RDWR means an append now fails for a registry that is
writable but not readable by the process (the old write-only open succeeded); that case now raises instead.
