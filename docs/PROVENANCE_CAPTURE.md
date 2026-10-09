# Endpoint-to-weights provenance capture (UNRUN on a real server)

`scripts/capture_provenance.py` records which weights a locally served model is actually using, for the serving host to run once and keep the report. **Status: UNRUN against any real model server.** There is no serving host in the build sandbox (2 CPU, ~1 GB RAM, no llama.cpp/Ollama). Its logic is tested only with fake loopback servers, temp files and child processes (`tests/test_capture_provenance.py`, 11 tests). Nothing here claims a real model was reached, hashed or bound.

## What it does
No prompt is ever sent. It does GET `<base>/models` (and GET `/props`; with `--ollama-tag`, POST `/api/show`) on a loopback URL only, hashes the weights file(s) you name, and with `--pid` checks whether the server process holds those files open or mapped. It reports three findings and never merges them:

| finding | meaning | what it does NOT show |
|---|---|---|
| reachability | endpoint answered; served name listed or not | which weights are loaded |
| weights | sha256 and size of each named file; match against `--expect-sha256` | what the server loaded |
| binding | `confirmed` only if ALL hold: an `--expect-sha256` matched the file; the `--pid` process holds that exact file (same device+inode, not a "(deleted)"/replaced mapping) open or mapped; and `--pid` owns the listening socket for the base-url port or is a descendant/ancestor of the process that does (Ollama's runner is a child of the :11434 server). Otherwise `unverified` | which tensors answered a request; the pid link is operator-asserted whenever the port relation is not `same`/descendant/ancestor |

Until a real run exists, read "binding confirmed" as: a process tied to this port holds the exact file inode that hashes to the expected value. It is not proof of endpoint-to-weights for any particular request.

Loopback only: it refuses any URL that is not `http://127.0.0.1|localhost|::1:<port>`, does not follow redirects, sends no credentials. Exit code 0 = every requested check passed, 1 = a check failed, 2 = usage error.

External values: the Ornith revision and file hashes and the hermes3 blob hash below were read from the Hugging Face API and registry.ollama.ai on 2026-10-09 by a read-only fetch. They are external and not independently verified by hashing the real files here.

## Prerequisites (on the serving host)
- Python 3.10+, standard library only. Linux for `--pid` (reads `/proc/<pid>/fd` and `/maps`; same user or root); everything else is portable.
- The model already served on loopback (OpenAI-compatible): llama.cpp `llama-server` (usually `http://127.0.0.1:8080/v1`) or Ollama (`http://127.0.0.1:11434/v1`).
- The GGUF file(s) readable on that host (llama.cpp). For Ollama the weights are blobs under `~/.ollama/models/blobs/sha256-<digest>` (or the service user's directory); pass that blob path.
- The server's PID (`pgrep -f llama-server`, `pgrep ollama`). For Ollama the model runner can be a child process; use the PID that actually has the blob mapped (`lsof -p <pid> | grep blobs`), and note that an idle Ollama may unload the model: send one request first (outside this script) or expect `unverified`.

## Commands
llama.cpp, Ornith Q4_K_M (expected hash from the Hub card for revision abdd624b12ebf020b767fff532ff44fe552b28c3):
```
python3 scripts/capture_provenance.py --base-url http://127.0.0.1:8080/v1 --served-name <name you started it with> \
  --weights /path/Ornith-1.5-9B-Q4_K_M.gguf \
  --expect-sha256 Ornith-1.5-9B-Q4_K_M.gguf=70c112196e0b7023803c9762752e46d29e612a92c83f995bc3ba1ceb07e8fab6 \
  --pid <llama-server pid> --out ornith-provenance.json
```
Ollama, hermes3:3b (blob sha256 read from registry.ollama.ai on 2026-10-09):
```
python3 scripts/capture_provenance.py --base-url http://127.0.0.1:11434/v1 --served-name hermes3:3b --ollama-tag hermes3:3b \
  --weights ~/.ollama/models/blobs/sha256-f616bb4104f36158e1838a5065618f7eba8437504250e80f9a9c51b373f4f1d4 \
  --expect-sha256 sha256-f616bb4104f36158e1838a5065618f7eba8437504250e80f9a9c51b373f4f1d4=f616bb4104f36158e1838a5065618f7eba8437504250e80f9a9c51b373f4f1d4 \
  --pid <ollama runner pid> --out hermes-provenance.json
```

## Expected output (shape only, from the fake-server tests; not a real run)
JSON with keys `reachability`, `llama_cpp_props`, `ollama_show` (if asked), `weights.files[]` (`path`, `sha256`, `bytes`, `expected_sha256`, `matches_expected`), `binding` (`verdict`, `pid`, `cmdline`, `named_files_held_open_or_mapped`, `reason`), `checks`, `all_requested_checks_passed`. A fully good run has `served_name_listed: true`, every `matches_expected: true`, `binding.verdict: "confirmed"`, exit 0. `binding: unverified` is an honest outcome, not a pass: keep the report and say so.

## Limits
Binding is process-level evidence (file open/mapped), not proof of which tensors answered a request. llama.cpp may close the file after loading without `--mlock`/mmap, which yields `unverified`. Ollama's served name is a tag; the tie to weights is the blob digest, so also keep the `/api/show` body. The port check reads /proc/net/tcp{,6} and other processes' fds, so run as the server's user or root; PID namespaces and containers (host pid vs in-container pid) can make it `unverified`; filesystems with per-subvolume device numbers (e.g. btrfs) may make `maps` device matching fail, in which case the fd entry is the evidence. Hash checking a multi-GB file takes minutes on slow disks. Never run it against a non-loopback server (it refuses).
