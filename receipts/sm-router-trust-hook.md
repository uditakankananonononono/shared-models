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
