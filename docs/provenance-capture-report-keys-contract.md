# Provenance-capture report keys contract (docs alignment unit)

Execution base: `0d37dfc0f9aab7dde8858e7e1db62e33c17d737c` (pinned base AT AUTHORING; not a guarantee about current main).
Scope: the "Expected output" paragraph of `docs/PROVENANCE_CAPTURE.md` ONLY (line 43 at base). Product change: proposed only, in the separate `provenance-capture-report-keys-proposed.patch` (NOT applied; peer judgment and independent audit gate). Scripts are untouched; tests are untouched (SM-U-C owns tests).
Statements below are READ from the named source at the pinned base, not executed. Nothing here claims the script was served or run against a real model; the script itself is documented UNRUN on a real server, and this unit changes no such claim.

## The flaw (verified real, not assumed)

`docs/PROVENANCE_CAPTURE.md:43` describes the JSON report shape as:
`binding` (`verdict`, `pid`, `cmdline`, `named_files_held_open_or_mapped`, `reason`), inside a top-level key list of `reachability`, `llama_cpp_props`, `ollama_show` (if asked), `weights.files[]`, `checks`, `all_requested_checks_passed`.

`scripts/capture_provenance.py` emits something different (all line numbers at base):
- The key `named_files_held_open_or_mapped` appears NOWHERE in the script (grep count 0).
- The `--pid` branch (lines 241-243) emits `binding` with keys `pid`, `cmdline`, `process_error`, `port`, `pid_port_relation`, `exact_files_held`, `stale_or_replaced`, `verdict`, `reason`. The evidence-carrying keys are `exact_files_held` and `stale_or_replaced`; the doc names neither, and omits `process_error`, `port`, `pid_port_relation`.
- The no-`--pid` branch (line 215) emits `binding` with ONLY `verdict` and `reason`. The doc's single key list conflates the two branches.
- The top-level report object (line 174) always carries `status` and `base_url` in addition to the keys the doc lists; the doc omits both.

A reader following the doc to consume a report looks for a key that never exists and misses the two keys that carry the actual binding evidence.

## The fix (proposed, one paragraph)

Replace line 43's key lists so that:
- top level: `status`, `base_url`, `reachability`, `llama_cpp_props`, `ollama_show` (if asked), `weights.files[]` (`path`, `sha256`, `bytes`, `expected_sha256`, `matches_expected`), `binding`, `checks`, `all_requested_checks_passed`;
- `binding` with `--pid`: `verdict`, `pid`, `cmdline`, `process_error`, `port`, `pid_port_relation`, `exact_files_held`, `stale_or_replaced`, `reason`;
- `binding` without `--pid`: only `verdict` and `reason`.
The remainder of the paragraph (fully-good-run and honest-unverified sentences) is unchanged: it matches the source as read.

## Acceptance criteria (grep-verifiable, no execution)

1. Every key the fixed paragraph names is grep-present in `scripts/capture_provenance.py` at the pinned base.
2. The fixed paragraph names no key absent from the script (in particular `named_files_held_open_or_mapped` no longer appears).
3. The diff touches only `docs/PROVENANCE_CAPTURE.md`.

## Exact files read at base 0d37dfc0f9aab7dde8858e7e1db62e33c17d737c for this unit

- `docs/PROVENANCE_CAPTURE.md` (full)
- `scripts/capture_provenance.py` (full)
Earlier research context (same base lineage, read in the research round at ddf6181d): the other `scripts/` files, the Inkling docs, `instinct_models/router.py`, `instinct_models/providers.py` excerpts. Those reads informed scoping only; this unit's claims rest solely on the two files above, re-read at the pinned base.
