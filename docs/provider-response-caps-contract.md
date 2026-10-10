# Provider and health response caps (proposal, UNAPPLIED)

Base `46228ca8ee98603398951464bfbe36b1691dc746` (current peer main, verified by `git ls-remote origin refs/heads/main`; 0d37dfc0, 90b7da68, 555a8ce5 and dcfa10e8 packages are historical receipts). Proposal: `proposals/sm-caps.patch` (providers.py, health.py, and the existing-fixture edit in tests/test_jev_hardening.py). Prep only: authored, not run.
Content-overlap check (READ: `git diff --name-status dcfa10e8 46228ca8` = lexical.py modified, plus a lexical patch, receipts and test added; earlier ranges = adapters.py, router.py, provenance docs and their tests/receipts): none of providers.py, health.py or tests/test_jev_hardening.py changed.

## Behavior proposed
- Provider bodies: default cap 8 MiB (`DEFAULT_MAX_RESPONSE_BYTES`), configurable by constructor kwarg `max_response_bytes` on `_OpenAICompat`, `InklingHFRouter`, `JevEval`, `OpenClawOwner`, and by `max_bytes` on `http_json`, `_jev_http`, `_openclaw_http`. A cap must be a positive int (bool, zero, negative, str, None, float raise ValueError) at the constructors AND at the three direct public entry points `http_json`, `_jev_http` and `_openclaw_http`, which validate first, before building a request or touching the network (peer-required code change; a direct call used to reach the opener with a float or give a TypeError or a nonsense read for True/0).
- `OpenClawOwner` (providers.py `_openclaw_http`, its only default transport use): the configured cap is applied through `functools.partial(_openclaw_http, max_bytes=...)`, and `_openclaw_http` passes it to `http_json`.
- HF model list in health: separate cap, 64 MiB (`DEFAULT_MODEL_LIST_MAX_BYTES`), `probe(max_bytes=)`; other `_get` callers (whoami) default to 8 MiB. `max_bytes` is validated as a positive int with the same rule; `probe` reports a bad value as `{"ok": False, "error": "max_bytes must be a positive integer"}`.
- Whole-body monotonic deadline equal to the per-operation timeout; the per-recv socket timeout stays. The clock is checked before each read and after every read, including the terminal empty read, so a delayed EOF is "too slow", not success.
- Errors are generic and status-less: `ProviderError("provider response too large")` / `("provider response too slow")`; health raises ValueError with generic text that `probe` reports. No body, URL or size detail.
- Caps apply to the default transports only; an injected transport keeps its own limits.
- Bodies are read with `read1`; the read just past the cap is `read1(1)` at most.
- Existing-test edit (peer exception, specific): `FakeResponse` in tests/test_jev_hardening.py exposed `read()`; it now exposes a faithful `read1(n)` (up to n bytes, consumed, then b"" at EOF). Its three users keep every assertion unchanged.

## Deadline bound (corrected)
For a NON-chunked body, the worst case is about the timeout plus one per-operation window (one read1 = at most one socket read; each recv gets a fresh timeout window). This is NOT strict wall-clock.
For a chunked body, `read1` goes through `_read1_chunked` then `_get_chunk_left` and can make more than one socket read (chunk-size line, trailers via `fp.readline`). Chunk framing, header and trailer drip are NOT bounded by the helper deadline and are out of scope. The earlier general bound is superseded.

## Traced (Python 3.12.0 source, READ)
- urllib sets `req.timeout` (request.py:505) and passes it to the connection (:1313); `ProxyHandler` is in the default handlers (:575) and reads the environment (:787-796).
- http.client `connect` uses `_create_connection` (client.py:984-985); `read()` with no size calls unbounded `self.fp.read()` (:485); `read1` does at most one underlying read for non-chunked bodies (:649-661).
- socket.create_connection sets `sock.settimeout` (socket.py:833-834); `SocketIO.readinto` calls `recv_into` (:693-707).
- socketmodule.c `sock_call_ex` initialises its deadline per call (:923), so each recv gets a fresh timeout window.
Sources (observed this session):
- https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/urllib/request.py
- https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/http/client.py
- https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/socket.py
- https://raw.githubusercontent.com/python/cpython/v3.12.0/Modules/socketmodule.c
- https://docs.python.org/3.12/library/socket.html (Notes on socket timeouts)
The chunked-read finding (`_read1_chunked`, `_get_chunk_left`) is the peer's reading of fetched CPython 3.12 as relayed by main; I located `_read1_chunked` at client.py:687 but did not trace `_get_chunk_left` myself.

## NOT traced
Python 3.10, `proxy_bypass` platform behavior, and the chunked path beyond the above.

## UNPROVEN
Nothing was run: behavior tests in `proposals/tests/` and text tests are authored, not run. `read1` short-read behavior over TLS is assumed. The existing suite is unchanged only by reading.
