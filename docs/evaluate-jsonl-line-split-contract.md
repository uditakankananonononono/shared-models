# Evaluate JSONL line-split contract (SM candidate unit: evaluate.py line 14)

Execution base: `a4da7e5f34eaf30aadc69fc7360d06159e9c4763` (pinned base AT AUTHORING; this is not a guarantee about current main).
Scope: `instinct_models/training/evaluate.py` `_load_rows`, line 14 ONLY. No other splitlines site is in scope (catalog.py:84 parses robots.txt, where full line-boundary semantics are correct; the other two candidate leads are owned by other builders).
Companion tests: `tests/test_evaluate_jsonl_split.py` (authored, not run).
Product change: proposed only, in the separate `evaluate-jsonl-line-split-proposed.patch` (NOT applied; peer judgment and independent audit gate. Peer audit of round 1: landable after five text fixes, which this revision makes; proposal recommended adopt only after recheck, not yet adopted).
Statements below are READ from the named source, not executed.

## The flaw (verified real, not assumed)

Current (read): line 14 parses rows with `Path(jsonl_path).read_text(encoding="utf-8").splitlines()`.
`str.splitlines()` splits on `\r`, `\n`, `\r\n` AND on `\x0b`, `\x0c`, `\x1c`-`\x1e`, `\x85` (NEL), `\u2028` (LS), `\u2029` (PS).
JSON mandates escaping only U+0000-U+001F, so of splitlines' extra boundaries only U+0085, U+2028 and U+2029 may sit RAW inside a perfectly valid JSON string. A JSONL row whose `query` contains one of those characters literally is valid input, but `splitlines()` cuts the row in two. `_load_rows` fails fast: `json.loads` on the head fragment raises `ValueError` as `line N: not valid JSON`, and the tail fragment and all later rows are never consumed. Valid evaluation data is refused, and when a later row is the genuinely invalid one the failure surfaces at the cut row instead of the real one, with that row's number.
Evidence from source:
- `instinct_models/training/evaluate.py:14` - the splitlines() call.
- `instinct_models/training/adapters.py:41` - the sibling confirmation-log parser already uses `text.split("\n")`.
- `instinct_models/lexical.py:109` - the lexical parser already uses the same `text.split("\n")` form.
Correction to the sibling comment (peer audit FIX2): both sibling sites carry the comment "NOT splitlines(): U+2028, U+0085, \x0b, \x0c, \x1c-\x1e can sit raw inside a valid JSON string". The `\x0b`, `\x0c`, `\x1c`-`\x1e` part is FALSE: those are below U+0020 and must be escaped in JSON, so they cannot sit raw inside a valid JSON string. The valid-raw set is exactly U+0085, U+2028, U+2029. The sibling files are outside this unit's scope and are not touched here; the proposed patch below carries the narrowed, correct comment.
So the project has already decided this rule twice; evaluate.py is the missed third site, and the three parsers are currently inconsistent on the same input.

Decision: FIX - parse with `text.split("\n")`, carrying a narrowed one-line comment naming only U+0085, U+2028, U+2029. The proposed patch changes exactly one line plus that comment.
Reader/user view after the fix: a valid row keeps its characters and its line number; an invalid row is still rejected with its true file line.
Remaining documented limits:
- `\r\n` files keep working: `split("\n")` leaves a trailing `\r`, which `json.loads` accepts as whitespace and `line.strip()` skips when alone.
- `\r`-only (old-Mac) files ALSO keep working (peer audit FIX1): `Path.read_text` reads in universal-newlines mode (`newline=None`), which translates both `\r\n` and lone `\r` to `\n` before either splitter sees the text. There is no CR-only behavior change and no approval tradeoff; a CR-only compat test is included for the auditor to execute.
- Raw `\x0b`, `\x0c`, `\x1c`-`\x1e` inside a row are invalid JSON either way (they must be escaped); with `split("\n")` they now fail as one line with a truer line number instead of splitting first.
- Decoding stays `utf-8` strict; no BOM handling is added here (the confirmation log's BOM case, N2, is a different file and out of scope).

## Compatibility

By reading: every existing caller writes rows via `json.dumps` (default `ensure_ascii=True`, so non-ASCII is escaped and no raw boundary characters ever appear) with `\n` separators - `tests/test_calibration_sweep.py`, `tests/test_adapters_eval.py`, `tests/test_training_example_flow.py`. For `\n`-joined input the two splitters do NOT produce identical element sequences (peer audit FIX3): `splitlines()` omits the trailing empty element while `split("\n")` yields a final `""` element. The `if not line.strip(): continue` guard skips that element, so the ROW RESULTS are equivalent even though the element sequences differ. All existing evaluate tests remain valid UNMODIFIED.
