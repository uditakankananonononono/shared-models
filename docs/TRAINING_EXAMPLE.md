# End to end: confirmation log -> training rows -> held-out check

```python
from instinct_models.training import (JsonlConfirmationLog, build_needle_jsonl,
                                      evaluate_lexical, calibration_sweep)

log = JsonlConfirmationLog("atlas", "atlas_confirmations.jsonl")   # owner-confirmed rows only
manifest = build_needle_jsonl(log, "out/atlas_needle.jsonl")      # drops unconfirmed, cross-product, duplicate rows
print(manifest["rows"], manifest["dropped"], manifest["warnings"], log.skipped)
print(evaluate_lexical("out/atlas_needle.jsonl"))                 # exact / wrong / abstained on held-out rows
print(calibration_sweep("out/atlas_needle.jsonl")["sweep"])       # pick min_confidence from these numbers
```

Each log line: `{"id", "query", "tools", "call": {"name","arguments"} | null, "owner_decision": "confirmed|rejected|unreviewed", "private": true}`.
`call: null` with `confirmed` is an owner-confirmed "no tool applies" row. `build_needle_jsonl` needs at least one usable row, and `train_locally_only` is set when any row is private.
