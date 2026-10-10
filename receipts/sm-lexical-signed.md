# SM-LEXICAL-SIGNED-NUMBER-SAFETY: PREP-NORUN

Exact base: 90b7da6850683cfa990173184b57a5cfb6a509ff.
Source read at this base: instinct_models/lexical.py lines 20-30,164-199,220-238
and tests/test_lexical_inputs.py (full). No excluded source read.
Evidence: lexical.py:29 unsigned regex; :182-187 conversion; :197 substring gate.
Inferred: -12 becomes positive 12. Not runtime reproduced.

Seven synthetic regression methods authored first, NOT RUN. Separate UNAPPLIED
proposal adds optional sign and standalone-token boundaries; numeric grounding
uses the full successful token instead of normalized-value substring matching.
Product lexical.py is unchanged. No new public API or wiring is introduced.

Acceptance: -12 -> -12; signed decimals and explicit plus parsed; existing
positive behavior preserved; integer decimal rejected; attached/unsupported
forms omitted; missing required numeric value abstains. Parenthesis delimiters
are allowed. Numeric exponent, leading/trailing decimal point forms remain
unsupported and are omitted rather than parsed by substring.

Date-delimiter ambiguity: 2026-10-15 is not treated as three numbers or a negative
number. The entire attached token is omitted from numeric extraction. A later
standalone -12 can still be selected. No date intent is inferred. This policy is
reported here; no new result diagnostics API has been invented. Multiple valid
standalone numbers retain the existing first-token heuristic and are outside
this unit. Enum values and schema bounds/type validation remain unchanged.

Planned commands, NOT RUN:
- python -m unittest discover -s tests -p test_lexical_signed_numerics.py
  (base expected to fail; candidate only after peer applies the proposal)
- git apply --unidiff-zero --check proposals/sm-lexical-signed-UNAPPLIED.patch
- peer-owned existing lexical tests/regressions after application

Checks run: source text and proposal diff inspection, git diff --check, packaging
and hashes. No imports/compile/tests/product execution/application/push. Numeric
behavior and compatibility assertions remain unverified. Peer owns execution,
integration and independent verdict.

## Named audit-gap revision

Added leading-zero subcases -012 -> -12 and -00.5 -> -0.5 to the existing
negative-literal test. The normalized strings -12 / -0.5 are not substrings of
their source literals, so removing numeric_grounded is expected to fail those
assertions. Product proposal remains unchanged. This revision was not run.
Peer reported prior baseline/candidate/mutant results; those are not this
revision's evidence and no PASS is inherited. Date whole-token omission policy
was confirmed by peer; no date parts/year/negative components are harvested.

## Repin receipt, new identity

Repinned onto exact 90b7da6850683cfa990173184b57a5cfb6a509ff,
base tree 7e6470b39bc768531cd91c4bae1bbfc13ee92e02. Content-overlap
comparison against historical 0d37dfc base showed no changes on this unit's
product target or additive package paths. Added paths do not exist on new base.
Product target content is identical between these bases, checked with git diff.
No excluded source was read. Proposal bytes unchanged; no product edits applied.
Historical or peer-reported test results do not transfer. Tests/mutants/runtime
remain NOT RUN for this repinned identity. Peer owns fresh execution/verdict.
