# health._get proxy bypass (proposal, UNAPPLIED)

Base `bd5a999513031b1a6da08b8852fad4bc239682c2` (peer main verified with `git ls-remote origin refs/heads/main` at 13:27 IST; your relay named 72407f5a, which is an ancestor of this head, whose only later commit adds my caps prep as additive files). Earlier proxy packages (d369a07d on dcfa10e8, 62bf815a on 46228ca8) are historical.
Overlap check (READ: `git diff --name-status 46228ca8 bd5a9995` = the LoRA prep (4 files) and the caps prep (4 files) added; instinct_models unchanged): no overlap with health.py. The caps prep files landed blob-equal to f3643072 (checked per file).

READ: health.py `_get` builds `urllib.request.build_opener(_NoRedirect())` with no ProxyHandler. In CPython 3.12.0, `ProxyHandler` is in the default handler classes (request.py:575) and reads the environment through `getproxies()` (:787-796), so an environment proxy can carry the bearer key. Source: https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/urllib/request.py (observed).
Fix proposed (peer-approved shape): `build_opener(urllib.request.ProxyHandler({}), _NoRedirect())`. The same pattern is already used and tested for Jev at tests/test_jev_hardening.py:99-101.

One patch only, STACKED: `proposals/sm-proxy-stacked-on-caps.patch` applies AFTER the caps patch (`proposals/sm-caps.patch` of the caps final2 head f3643072, which includes the entry-point validation and the health validation), because the caps hunk edits adjacent lines in `_get`. It was generated against the caps-applied tree and checked with `git apply --check` after the caps patch on a clean 46228ca8 clone. It does not apply to bare dcfa10e8, and no standalone variant is shipped.

Test: `proposals/tests/test_health_proxy_structural.py` mocks `urllib.request.getproxies` to a SYNTHETIC non-empty dict, WRAPS the real `build_opener` and mocks `OpenerDirector.open`. It asserts the build_opener arguments hold exactly one explicit `ProxyHandler` with `proxies == {}` plus `_NoRedirect`, that `getproxies` was NOT called, and that the resulting opener has no proxy methods and keeps `_NoRedirect`. (Peer finding: the real build_opener drops an empty ProxyHandler from `opener.handlers` because it has no `*_open` methods, so the explicit handler is asserted on the arguments.) An ambient `ProxyHandler()` mutant would carry the synthetic proxies and fail, whatever the real environment holds. No live proxy, network or credentials.

NOT traced: Python 3.10, proxy_bypass platform behavior. UNPROVEN: the effect at runtime; tests are authored, not run.
