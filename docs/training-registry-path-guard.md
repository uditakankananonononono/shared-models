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
