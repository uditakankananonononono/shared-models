# health._get: no environment proxy (SM-APPLY-PROXY)

Parent `fc13bca2494b4e38482e829f12d865ca956f6390` (peer main, verified with `git ls-remote origin refs/heads/main` at 14:16 IST). Authored, not run (PREP-NORUN). Base-only: independent of the caps proposal, which stays UNAPPLIED; no caps behavior is active or claimed.

## Change
`instinct_models/health.py` line 41: `build_opener(_NoRedirect())` becomes `build_opener(urllib.request.ProxyHandler({}), _NoRedirect())`. One line.

## Why (READ)
`_get` sends `Authorization: Bearer <api key>` (health.py:38-39). With no ProxyHandler passed, CPython 3.12.0's `build_opener` adds its default `ProxyHandler`, which reads the environment through `getproxies()` (request.py:575, 787-796; https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/urllib/request.py). `providers.py:50` (http_json), `providers.py:408` (`_jev_opener`) and `scripts/capture_provenance.py:60` already pass `ProxyHandler({})`; health was the remaining bearer-carrying site.

## Behavior notes
- An explicit empty `ProxyHandler` has no `*_open` methods, so `build_opener` drops it from `opener.handlers` and also skips its default one (request.py:581-589). The test therefore asserts on the `build_opener` arguments and on the resulting opener's lack of proxy methods.
- Existing tests that hit real loopback servers (tests/test_health.py, test_health_never_raises.py) go direct either way (127.0.0.1). tests/test_health_key_guard.py patches `OpenerDirector.open`, which is unaffected.
- Tests that stay as they are: tests/test_health_proxy_text.py reads the old stacked proposal files in proposals/; it is not edited.

## Not covered
Python 3.10 and `proxy_bypass` platform behavior (not traced). No live proxy or network proof. Unbounded `r.read()` (health.py:43) stays as is: caps are a separate, deferred decision.
