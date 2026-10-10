# Evaluate JSONL line-split contract (SM candidate unit: evaluate.py line 14)

Execution base: `a4da7e5f34eaf30aadc69fc7360d06159e9c4763` (origin/main, matches the peer-stated main).
Scope: `instinct_models/training/evaluate.py` `_load_rows`, line 14 ONLY. No other splitlines site is in scope (catalog.py:84 parses robots.txt, where full line-boundary semantics are correct; the other two candidate leads are owned by other builders).
Companion tests: `tests/test_evaluate_jsonl_split.py` (authored, not run).
Product change: proposed only, in the separate `evaluate-jsonl-line-split-proposed.patch` (NOT applied; peer judgment and independent audit gate).
Statements below are READ from the named source, not executed.

## The flaw (verified real, not assumed)

Current (read): line 14 parses rows with `Path(jsonl_path).read_text(encoding="utf-8").splitlines()`.
`str.splitlines()` splits on `\r`, `\n`, `\r\n` AND on `\x0b`, `\x0c`, `\x1c`-`\x1e`, `\x85` (NEL), ` `, ` `.
JSON mandates escaping only U+0000-U+001F, so U+0085, U+2028 and U+2029 may sit RAW inside a perfectly valid JSON string. A JSONL row whose `query` contains one of those characters literally is valid input, but `splitlines()` cuts the row in two: the head fragment fails `json.loads` and the row is spuriously rejected as `line N: not valid JSON`, the tail fragment is treated as another row, and every later line number shifts. Valid evaluation data is refused with a misleading line number.
Evidence from source:
- `instinct_models/training/evaluate.py:14` - the splitlines() call.
- `instinct_models/training/adapters.py:41` - the sibling confirmation-log parser already uses `text.split("\n")` with the comment "NOT splitlines(): U+2028, U+0085, \x0b, \x0c, \x1c-\x1e can sit raw inside a valid JSON string".
- `instinct_models/lexical.py:109` - the lexical parser already uses the same `text.split("\n")` fix with the same comment.
So the project has already decided this rule twice; evaluate.py is the missed third site, and the three parsers are currently inconsistent on the same input.

Decision: FIX - parse with `text.split("\n")`, carrying the same one-line comment as the sibling sites. The proposed patch changes exactly one line plus that comment.
Reader/user view after the fix: a valid row keeps its characters and its line number; an invalid row is still rejected with its true file line.
Remaining documented limits:
- `\r\n` files keep working: `split("\n")` leaves a trailing `\r`, which `json.loads` accepts as whitespace and `line.strip()` skips when alone.
- Old-Mac `\r`-only files change behavior: they now read as ONE line and fail as `line 1: not valid JSON` instead of parsing. Accepted: JSONL is `\n`-delimited, and the previous acceptance was incidental.
- Raw `\x0b`, `\x0c`, `\x1c`-`\x1e` inside a row are invalid JSON either way; with `split("\n")` they now fail as one line with a truer line number instead of splitting first.
- Decoding stays `utf-8` strict; no BOM handling is added here (the confirmation log's BOM case, N2, is a different file and out of scope).

## Compatibility

By reading: every existing caller writes rows via `json.dumps` (default `ensure_ascii=True`, so non-ASCII is escaped and no raw boundary characters ever appear) with `\n` separators - `tests/test_calibration_sweep.py`, `tests/test_adapters_eval.py`, `tests/test_training_example_flow.py`. For `\n`-joined ASCII input, `split("\n")` and `splitlines()` produce the same element sequence, including the skipped trailing empty string. All existing evaluate tests remain valid UNMODIFIED.
