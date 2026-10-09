#!/usr/bin/env python3
"""Capture endpoint-to-weights provenance for a LOCALLY served model. Standard library only, Linux for the process check.

STATUS: UNRUN against a real model server. Its logic is exercised only by tests/test_capture_provenance.py with fake servers
and files. It makes no claim about any real model until someone runs it on the serving host.

It sends NO prompt. It only does GET /v1/models (and optionally /props, /health, POST /api/show for Ollama) on a loopback URL,
hashes the weights file(s) you name, and (with --pid) checks whether that server process actually has those files open or mapped.
Three separate findings, never merged:
  reachability - the endpoint answered and listed the served model name (protocol evidence only)
  weights      - sha256/size of each named file, compared to --expect-sha256 values if given (file identity only)
  binding      - "confirmed" ONLY when ALL hold: (a) --expect-sha256 was given for a file and the file's hash matches it; (b) the --pid process
                 has that exact file (same device+inode, not a "(deleted)" replaced mapping) open or mapped; (c) --pid owns the listening socket
                 for the base-url port, or is a descendant/ancestor of the process that does (covers Ollama's runner). Otherwise "unverified".
                 Even "confirmed" means "a process tied to this port holds the exact file inode that hashes to the expected value": it does
                 not prove which tensors answered a request. Linux /proc only; PID-namespace/container setups can make the check unverified.
Exit code: 0 = every requested check passed, 1 = a check failed, 2 = usage error (e.g. non-loopback URL).
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

LOOPBACK_NAMES = {"localhost"}


def require_loopback(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    host = u.hostname or ""
    ok = u.scheme == "http" and u.port is not None and (host in LOOPBACK_NAMES or _is_loopback_ip(host))
    if not ok:
        raise ValueError("base URL must be http://<127.0.0.1|localhost|::1>:<port>[/v1]")
    return url.rstrip("/")


def _is_loopback_ip(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def http(url: str, body: dict | None = None, timeout: float = 10) -> tuple[int | None, str, str | None]:
    """(status, body_text, error). Never raises. No credentials are sent."""
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(req, timeout=timeout) as r:
            return r.status, r.read(5_000_000).decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, "", f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - report, never crash the capture
        return None, "", type(e).__name__


def sha256_file(path: str) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def process_files(pid: int) -> dict:
    """Files the process has open (fd) or mapped (maps), each with device+inode and a deleted/replaced flag.
    Needs permission to read /proc/<pid>."""
    out: dict = {"entries": [], "cmdline": None, "error": None}
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            out["cmdline"] = [x.decode("utf-8", "replace") for x in f.read().split(b"\0") if x]
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                link = os.readlink(f"/proc/{pid}/fd/{fd}")
                if not link.startswith("/"):
                    continue
                st = os.stat(f"/proc/{pid}/fd/{fd}")  # the inode the process really holds, even if the path was replaced
                out["entries"].append({"via": "fd", "path": link.removesuffix(" (deleted)"), "dev": st.st_dev, "ino": st.st_ino,
                                       "deleted": link.endswith(" (deleted)")})
            except OSError:
                pass
        with open(f"/proc/{pid}/maps") as f:
            for line in f:
                parts = line.split(None, 5)
                if len(parts) == 6 and parts[5].startswith("/") and parts[4] != "0":
                    major, minor = (int(x, 16) for x in parts[3].split(":"))
                    path = parts[5].strip()
                    out["entries"].append({"via": "maps", "path": path.removesuffix(" (deleted)"), "dev": os.makedev(major, minor),
                                           "ino": int(parts[4]), "deleted": path.endswith(" (deleted)")})
    except (OSError, ValueError) as e:
        out["error"] = f"{type(e).__name__}: cannot read /proc/{pid} (wrong pid, no permission, or not Linux)"
    return out


def _ppid_map() -> dict[int, int]:
    m = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                with open(f"/proc/{d}/stat") as f:
                    m[int(d)] = int(f.read().rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                pass
    return m


def listener_pids(port: int) -> set[int]:
    """PIDs (readable by us) that hold a LISTEN socket on this local TCP port."""
    inodes = set()
    for tbl in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(tbl) as f:
                next(f)
                for line in f:
                    c = line.split()
                    if c[3] == "0A" and int(c[1].rsplit(":", 1)[1], 16) == port:
                        inodes.add(c[9])
        except (OSError, ValueError, IndexError):
            pass
    pids = set()
    for d in os.listdir("/proc") if inodes else []:
        if d.isdigit():
            try:
                for fd in os.listdir(f"/proc/{d}/fd"):
                    if os.readlink(f"/proc/{d}/fd/{fd}") in {f"socket:[{i}]" for i in inodes}:
                        pids.add(int(d))
                        break
            except OSError:
                pass
    return pids


def pid_port_relation(pid: int, port: int) -> str:
    """'same', 'pid_is_descendant_of_listener', 'listener_is_descendant_of_pid', 'listener_not_found' or 'unrelated'."""
    owners = listener_pids(port)
    if not owners:
        return "listener_not_found"
    if pid in owners:
        return "same"
    ppid = _ppid_map()

    def descends(child: int, ancestor: int) -> bool:
        seen = set()
        while child in ppid and child not in seen and child > 1:
            seen.add(child)
            child = ppid[child]
            if child == ancestor:
                return True
        return False

    if any(descends(pid, o) for o in owners):
        return "pid_is_descendant_of_listener"
    if any(descends(o, pid) for o in owners):
        return "listener_is_descendant_of_pid"
    return "unrelated"


def capture(base_url: str, served_name: str | None, weights: list[str], expect: dict[str, str] | None = None,
            pid: int | None = None, ollama_tag: str | None = None, timeout: float = 10) -> dict:
    base = require_loopback(base_url)
    expect = expect or {}
    rep: dict = {"status": "UNRUN-ON-REAL-SERVER unless you ran it yourself on the serving host", "base_url": base, "checks": {}}
    st, body, err = http(base + "/models", timeout=timeout)
    models, listed = [], None
    try:
        data = json.loads(body) if body else None
        models = [m.get("id") for m in (data or {}).get("data", []) if isinstance(m, dict)]
    except (ValueError, AttributeError):
        err = err or "response was not JSON"
    if served_name is not None:
        listed = served_name in models
    rep["reachability"] = {"get_models_status": st, "error": err, "models_listed": models, "served_name_asked": served_name,
                           "served_name_listed": listed, "models_response_sha256": hashlib.sha256(body.encode()).hexdigest() if body else None,
                           "note": "protocol evidence only; says nothing about which weights are loaded"}
    rep["checks"]["reachable"] = st == 200 and err is None
    if served_name is not None:
        rep["checks"]["served_name_listed"] = bool(listed)
    props = http(base.rsplit("/v1", 1)[0] + "/props", timeout=timeout)  # llama.cpp server; absent elsewhere
    rep["llama_cpp_props"] = {"status": props[0], "body": props[1][:4000] if props[0] == 200 else None}
    if ollama_tag:
        show = http(base.rsplit("/v1", 1)[0] + "/api/show", {"model": ollama_tag}, timeout=timeout)
        rep["ollama_show"] = {"status": show[0], "error": show[2], "body_sha256": hashlib.sha256(show[1].encode()).hexdigest() if show[1] else None,
                              "body": show[1][:6000] if show[0] == 200 else None}
        rep["checks"]["ollama_show_ok"] = show[0] == 200
    files = []
    for p in weights:
        try:
            digest, size = sha256_file(p)
            f = {"path": os.path.realpath(p), "sha256": digest, "bytes": size}
        except OSError as e:
            f = {"path": p, "error": type(e).__name__}
            rep["checks"][f"readable:{os.path.basename(p)}"] = False
            files.append(f)
            continue
        want = expect.get(os.path.basename(p)) or expect.get(digest)
        if want is not None:
            f["expected_sha256"] = want
            f["matches_expected"] = want.lower() == digest
            rep["checks"][f"sha256_matches:{os.path.basename(p)}"] = f["matches_expected"]
        files.append(f)
    rep["weights"] = {"files": files, "note": "file identity only; says nothing about what the server loaded"}
    if pid is None:
        rep["binding"] = {"verdict": "unverified", "reason": "no --pid given: nothing ties the served name to these files"}
    else:
        pf = process_files(pid)
        port = urllib.parse.urlsplit(base).port
        relation = pid_port_relation(pid, port)
        ids = {}
        for f in files:
            if "sha256" in f:
                st = os.stat(f["path"])
                ids[(st.st_dev, st.st_ino)] = f
        exact, stale = [], []
        for e in pf["entries"]:
            f = ids.get((e["dev"], e["ino"]))
            if f is not None and not e["deleted"]:
                exact.append({"path": f["path"], "via": e["via"], "matches_expected": f.get("matches_expected")})
            elif any(e["path"] == g["path"] for g in ids.values()):
                stale.append({"path": e["path"], "via": e["via"], "deleted": e["deleted"], "reason": "process holds a different or replaced inode at this path"})
        hash_ok = any(x["matches_expected"] is True for x in exact)
        port_ok = relation in ("same", "pid_is_descendant_of_listener", "listener_is_descendant_of_pid")
        reasons = []
        if not exact:
            reasons.append("process does not hold the exact hashed file inode" + (" (it holds a stale/replaced mapping of that path)" if stale else ""))
        if exact and not hash_ok:
            reasons.append("no --expect-sha256 matched the held file: a hash was not compared against an external expectation")
        if not port_ok:
            reasons.append(f"pid is not tied to the listening port ({relation}); pid link is operator-asserted only")
        rep["binding"] = {"pid": pid, "cmdline": pf["cmdline"], "process_error": pf["error"], "port": port, "pid_port_relation": relation,
                          "exact_files_held": exact, "stale_or_replaced": stale,
                          "verdict": "confirmed" if (exact and hash_ok and port_ok) else "unverified",
                          "reason": "; ".join(reasons) or "expected hash matched, exact inode held, pid tied to the listening port"}
        rep["checks"]["binding_confirmed"] = rep["binding"]["verdict"] == "confirmed"
    rep["all_requested_checks_passed"] = all(rep["checks"].values()) if rep["checks"] else False
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:8080/v1 or http://127.0.0.1:11434/v1 (loopback only)")
    ap.add_argument("--served-name", help="the model name the product will send; checked against GET /v1/models")
    ap.add_argument("--weights", action="append", default=[], help="path to a weights file the server should be using (repeatable)")
    ap.add_argument("--expect-sha256", action="append", default=[], metavar="NAME_OR_SHA=SHA256",
                    help="expected hash, keyed by file basename (e.g. Ornith-1.5-9B-Q4_K_M.gguf=70c1...) (repeatable)")
    ap.add_argument("--pid", type=int, help="server process id, to check it holds the weights open/mapped (Linux)")
    ap.add_argument("--ollama-tag", help="Ollama tag (e.g. hermes3:3b): also record POST /api/show")
    ap.add_argument("--out", help="write the JSON report here (default: stdout)")
    a = ap.parse_args(argv)
    try:
        expect = dict(x.split("=", 1) for x in a.expect_sha256)
        rep = capture(a.base_url, a.served_name, a.weights, expect, a.pid, a.ollama_tag)
    except ValueError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return 2
    text = json.dumps(rep, indent=2, sort_keys=True)
    (open(a.out, "w") if a.out else sys.stdout).write(text + "\n")
    return 0 if rep["all_requested_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
