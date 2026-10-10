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
including null, false, zero, empty strings and empty lists, are skipped with
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
package export has been changed. Explicit null arguments are rejected in this
candidate rather than normalized to `{}`; this is the strict interpretation of
"non-object arguments" and is an intentional compatibility change for peer
review. Absent arguments remain compatible.

Python JSON recursion behavior and all assertions are unverified because tests
were authored but not run. This handles recursion raised by decoding, not a
new maximum-depth policy for parseable input. Byte size, row count and execution
time limits are outside this unit. No live/hosted calls, services, database,
migrations, environment/credential inspection or pushes are part of this work.
