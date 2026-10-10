# Hostile confirmation-log reader: preparation contract

Unit: SM-U-C-HOSTILE-ADAPTER-LOG. Base commit:
`e2fea28f82b95aea44875a4d0730fc787178c068`.

INTEGRATION STATUS (integrator, 2026-10-10): the peer prepared this as an opt-in sibling class and ran nothing. It was applied, run and integrated: the hardened logic now IS `adapters.JsonlConfirmationLog` (the default reader every caller already uses), and `adapters_hostile.HardenedJsonlConfirmationLog` is an alias. Two integration decisions: (1) an explicit `"arguments": null` means no arguments ({}), as the legacy reader and the dataset builder treat it; other non-object values (false, 0, "", [], strings, numbers, lists) are skipped rows; (2) a non-list `tools` and a non-UTF-8 file are now rejected at read time (skipped row / file-level ValueError) where the legacy reader let a bad `tools` through to the builder. The rest of this document is the peer's original contract text; where it says null arguments are rejected, decision (1) overrides it.

## Explicit interface

Import `HardenedJsonlConfirmationLog` from
`instinct_models.training.adapters_hostile` and construct it with
`(product: str, path: str | pathlib.Path)`. Supported products remain `atlas`,
`meemee` and `sugarcode`. Public attributes are `product`, `path`, and `skipped`.
`rows()` lazily yields the existing `dataset.ExampleRow` objects and resets
`skipped` when iteration starts. `skipped` holds dictionaries containing
`source_ref` (file basename and physical line number) and a content-free reason.
This implements the existing `DomainDataset` shape; no new shared API is needed.

The whole file is read as strict UTF-8 before any row is yielded. Invalid bytes
raise a file-level `ValueError("confirmation log is not valid UTF-8")` without
raw data or an explicit exception cause. Other filesystem exceptions retain
normal Python behavior. This is not a streaming or resource-quota reader.

Blank lines are ignored. JSON parser recursion failures are skipped with reason
`unreadable row: RecursionError`. A non-list `tools` value is skipped with reason
`tools must be a list`. A non-object, non-null `call` is skipped with reason
`call must be an object or null`. Present non-object `arguments` values,
including false, zero, empty strings and empty lists (but NOT an explicit null, which means `{}`), are skipped with
reason `arguments must be an object`. Missing arguments still default to `{}`.
A null or missing call still means an off-topic row with no answers.
Other malformed JSON, missing required fields and wrong top-level shapes retain
content-free exception-type reasons. One bad row does not stop later rows.

## Compatibility preserved

The reader copies explicit `product` values unchanged, including null, and only
supplies the selected product when the key is missing. The existing
`build_needle_jsonl` remains responsible for dropping rows tagged for another
product, rejecting unconfirmed rows, checking detailed tool/query/argument
semantics and strict serialization. Product tags are never overwritten to
make a foreign-product row look local. The authored tests exercise the existing
builder directly to assert its foreign-product drop reason and exported rows.
Existing source ID fallback, privacy default and owner-confirmation comparisons
are preserved. List element validation for tools remains with the builder.

## Decisions and unverified areas

The peer must decide whether and where to select this reader, and whether to
rename/replace the legacy reader in a later integration change. No caller or
package export has been changed. Explicit null arguments mean `{}` (integrator decision, matching the legacy reader and the dataset builder). Absent arguments remain compatible. Rows are split on `\n` only, so a row containing a raw U+2028 or U+0085 inside a string is read, not split in two.

The tests were run by the integrator (see the commit and report). This handles recursion raised by decoding, not a
new maximum-depth policy for parseable input. Byte size, row count and execution
time limits are outside this unit: the whole file is read into memory. NaN is accepted as a JSON value. No live/hosted calls, services, database,
migrations, environment/credential inspection or pushes are part of this work.

## Intake diagnostics (SM-N6)

- UTF-16: a file that starts with a UTF-16 BOM (FF FE / FE FF), or whose first 64 bytes are NUL-interleaved ASCII, raises a
  file-level ValueError telling the user to re-save as UTF-8 (PowerShell `>` writes UTF-16). UTF-16 is NOT decoded. The
  message echoes no content. Detection is a heuristic: UTF-16 text that is not mostly ASCII in its first 64 bytes and has no
  BOM is not recognized and falls to the generic "not valid UTF-8" error. A UTF-32 BOM also trips the UTF-16 message.
- Size cap: constructor `max_bytes` (default 256 MiB). The size is read with fstat on the open descriptor and the read is
  itself bounded to max_bytes+1, so a file that grows after the check is still refused. This is a guard against huge files,
  not a streaming reader: decoding and splitting hold the text, so peak memory is a few times the cap.
- Non-finite numbers: NaN, Infinity, -Infinity and out-of-range floats such as 1e999 anywhere in a row (arguments, query,
  tools) skip that row with reason "non-finite number (NaN or Infinity)" and its line number. The builder already dropped
  such rows later without saying which; the set of trained rows does not change.
- Duplicate ids: rows are never dropped for a repeated `id`. `warnings` (reset on each pass) lists each repeat with its line
  and the line of first sight. Missing, empty, boolean and non-scalar ids are not tracked. Two rows with the same id and
  different content both stay; the downstream dedup is unchanged.
- The reader no longer calls Path.read_text; it decodes bytes itself with utf-8-sig (strict). Symlinks are still followed
  (unchanged); this is not a no-follow reader.
