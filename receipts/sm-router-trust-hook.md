# SM-ROUTER-TRUST-HOOK-ISOLATION: PREP-NORUN

Exact base: 0d37dfc0f9aab7dde8858e7e1db62e33c17d737c.
Files read at this base: instinct_models/router.py and tests/test_router_result_guard.py.
Evidence: router.py:70-72 invokes private policy before try at :73.
Inferred consequence: a hook exception aborts fallback. Not runtime reproduced.

First commit authors synthetic tests expected to fail on the base; not run.
Separate proposal file moves the policy check inside the existing exception
boundary. Product router.py itself is unchanged. No training/providers/health
source read. The proposal is UNAPPLIED, not an integrated repair.

Acceptance: hook exceptions are generic errors, never permission or denial;
no availability/chat on that provider, then next trusted provider. False policy
still skips; public tasks never call policy. Private details never enter attempts.

Planned commands, NOT RUN:
- python -m unittest discover -s tests -p test_router_trust_hook_isolation.py
  (base should fail; candidate should pass only after peer applies proposal)
- git apply --check proposals/sm-router-trust-hook-UNAPPLIED.patch
- peer-owned router isolation/regression suite after application

Checks run: text inspection, git diff --check and packaging/receipt commands only.
Tests, imports, compilation and candidate code: NOT RUN. No pushes or live state.

## Applied at landing (integrator, 2026-10-10)

The proposal in proposals/sm-router-trust-hook-UNAPPLIED.patch was APPLIED by the integrator as a separate commit on top of
main 90b7da68 (the patch file is kept as the peer's authored artifact). Measured by the integrator: before application the new
test file has 3 errors of 4 (suite 346 with 3 errors); after application the full suite is 346/346 OK. The existing router
isolation and result-guard tests pass. Synthetic local proof only: no live provider, private transport or real policy hook
was exercised.
