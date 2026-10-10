"""Per-product training data -> Needle fine-tune JSONL.

The pipeline is shared; each product supplies its own ``DomainDataset`` (Atlas:
owner-confirmed receipts/proposals/obligations/experiment decisions; Meemee:
personal-agent data; Sugarcode: its own). Rules enforced here, from Needle's
finetuning guide: arguments must be literally present in the query, optional
fields without evidence are omitted, and off-topic rows (``answers: []``) are
kept at roughly 1 in 8. Rows not marked confirmed are dropped; private rows are
kept but the manifest records that the dataset must train locally.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol


@dataclass
class ExampleRow:
    query: str
    tools: list[dict]
    answers: list[dict]
    confirmed: bool
    source_ref: str
    private: bool = True
    reasoning: str | None = None
    system: str | None = None
    meta: dict = field(default_factory=dict)
    product: str | None = None  # set by the product; rows tagged for another product are dropped


class DomainDataset(Protocol):
    product: str

    def rows(self) -> Iterable[ExampleRow]:
        """The product's own training rows (confirmed and tagged with the product)."""


def _values(obj) -> list[str]:
    if isinstance(obj, dict):
        return [v for x in obj.values() for v in _values(x)]
    if isinstance(obj, list):
        return [v for x in obj for v in _values(x)]
    if isinstance(obj, bool) or obj is None:
        return []
    return [str(obj)]


def check_row(row: ExampleRow) -> str | None:
    if not isinstance(row.query, str):
        return "query must be text"
    if not isinstance(row.tools, list) or not all(isinstance(t, dict) for t in row.tools):
        return "tools must be a list of objects"
    if not isinstance(row.answers, list) or not all(isinstance(c, dict) for c in row.answers):
        return "answers must be a list of objects"
    if any(not isinstance(t.get("name"), str) or not t["name"].strip() for t in row.tools):
        return "every tool needs a non-empty text name"
    names = {t.get("name") for t in row.tools}
    if len(names) != len(row.tools):
        return "duplicate tool name"
    for call in row.answers:
        if not isinstance(call.get("name"), str):
            return "answer call name must be text"
        if call.get("name") not in names:
            return f"answer calls unknown tool {call.get('name')!r}"
        args = call.get("arguments", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return f"arguments for {call.get('name')!r} must be an object"
        for v in _values(args):
            if not v.strip():
                return "blank argument value (omit optional fields without evidence)"
            if v.casefold() not in row.query.casefold():
                return f"argument value {v!r} is not present in the query"
    if row.reasoning is not None and not isinstance(row.reasoning, str):
        return "reasoning must be text"
    if row.system is not None and not isinstance(row.system, str):
        return "system must be text"
    if not row.query.strip():
        return "empty query"
    return None


def _check_output_target(path: Path) -> None:
    """Refuse a symlink or non-regular file at an output path (so a planted link is never written through)."""
    if path.is_symlink():
        raise ValueError(f"refusing to write through a symlink: {path.name}")
    if path.exists() and not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"output path exists and is not a regular file: {path.name}")


def _fsync_dir(directory: Path) -> None:
    """fsync a directory, ordering a rename into it before any later crash (POSIX only)."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


_IS_POSIX = os.name == "posix"  # module constant so tests can exercise the non-POSIX branch without breaking pathlib


def _is_trusted_system_symlink(path: Path, _depth: int = 0) -> bool:
    """COMPATIBILITY EXCEPTION, not a safety proof. Based on REPORTED ownership and mode only: the link is root-owned
    (st_uid == 0) and sits in a parent that is root-owned and not group/other-writable (macOS /var -> /private/var,
    /tmp, /etc live in /; Linux /var/run in /var). This is NOT a verified system location, NOT a protected parent or
    target chain, and NOT no-follow access: the write goes through the link's destination, whose directory contents and
    permissions are not inspected, and a race between check and use remains. It does follow the link's own target chain
    (a link or ancestor of the target that is itself a symlink must also qualify, to a depth of 8), so a root-owned link
    pointing at a user-owned symlink is refused. POSIX only: Windows reports st_uid 0 for everything."""
    if not _IS_POSIX or _depth > 8:
        return False
    link, parent = path.lstat(), path.parent.lstat()
    if not (link.st_uid == 0 and parent.st_uid == 0 and not (parent.st_mode & 0o022)):
        return False
    target = Path(os.path.normpath(path.parent / os.readlink(path)))
    return all(not q.is_symlink() or _is_trusted_system_symlink(q, _depth + 1) for q in (target, *target.parents))


def _check_no_symlink_ancestors(directory: Path) -> None:
    """Refuse when the output directory is a symlink, or when any ancestor is a symlink that does not pass
    _is_trusted_system_symlink. Lexical check with a check/open race; see docs/dataset-output-durability-contract.md.
    The immediate directory is refused even if it looks like such a link."""
    for p in (directory, *directory.parents):
        if p.is_symlink():
            if p == directory:
                raise ValueError("refusing to write into a symlinked output directory")
            if _is_trusted_system_symlink(p):
                continue  # keep walking: a non-qualifying link higher up must still be refused
            raise ValueError(f"refusing to write through a symlinked ancestor directory: {p}")


def _write_atomic(path: Path, data: str | bytes) -> None:
    """Write via a fresh temp file in the same directory, then rename over the target (never a partial file at the target).

    Guarantee: a directory at the temp name, or an OSError while clearing the temp name, is a name-only ValueError.
    Limitation, deliberately not widened here: a PermissionError from reading the temp name's status (lstat, e.g. an
    unreadable parent directory) is not normalized and surfaces as-is, including its path and errno text."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        if stat.S_ISDIR(tmp.lstat().st_mode):  # lstat: a symlink to a directory is a link, handled by unlink below
            raise ValueError(f"output temp path is a directory: {tmp.name}")
    except FileNotFoundError:
        pass
    try:
        tmp.unlink(missing_ok=True)  # stale or planted file/symlink at our own temp name: remove the name (never follows a link), then create exclusively
    except OSError:
        raise ValueError(f"cannot clear output temp path: {tmp.name}") from None
    payload = data.encode("utf-8") if isinstance(data, str) else data  # raw bytes pass through (prior content need not be UTF-8)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o666)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())  # contents written out before the rename
        os.replace(tmp, path)
        if os.name == "posix":
            _fsync_dir(path.parent)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass  # cleanup must never mask the primary write error
        raise


def build_needle_jsonl(dataset: DomainDataset, out_path: str | Path, *, min_off_topic_ratio: float = 0.1) -> dict:
    kept, dropped, off_topic, private = [], [], 0, False
    seen: set[str] = set()
    for row in dataset.rows():
        if not row.confirmed:
            dropped.append({"source_ref": row.source_ref, "reason": "not owner-confirmed"})
            continue
        if row.product is not None and row.product != dataset.product:
            dropped.append({"source_ref": row.source_ref,
                            "reason": f"row belongs to {row.product!r}, not {dataset.product!r}"})
            continue
        why = check_row(row)
        if why:
            dropped.append({"source_ref": row.source_ref, "reason": why})
            continue
        rec = {"query": row.query, "tools": row.tools, "answers": row.answers}
        if row.reasoning:
            rec["reasoning"] = row.reasoning
        if row.system:
            rec["system"] = row.system
        try:
            key = json.dumps(rec, sort_keys=True, ensure_ascii=False, allow_nan=False)
            key.encode("utf-8")
        except (TypeError, ValueError, RecursionError):
            dropped.append({"source_ref": row.source_ref, "reason": "row is not strict-JSON / UTF-8 serializable"})
            continue
        if key in seen:
            dropped.append({"source_ref": row.source_ref, "reason": "duplicate of an earlier row"})
            continue
        seen.add(key)
        kept.append(rec)
        off_topic += not row.answers
        private = private or row.private
    if not kept:
        raise ValueError("no usable rows after filtering")
    ratio = off_topic / len(kept)
    out = Path(out_path)
    manifest_path = Path(str(out) + ".manifest.json")
    _check_no_symlink_ancestors(out.parent)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except (NotADirectoryError, FileExistsError) as exc:
        raise ValueError("output directory path is blocked by a file") from exc
    _check_output_target(out)  # both targets are checked before anything is written
    _check_output_target(manifest_path)
    text = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in kept)
    manifest = {"product": dataset.product, "rows": len(kept), "dropped": len(dropped), "dropped_detail": dropped[:200],
                "off_topic_ratio": round(ratio, 3), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "train_locally_only": private, "path": str(out),
                "warnings": ([f"off-topic ratio {ratio:.2f} is below {min_off_topic_ratio}; the tuned model may call tools on everything"]
                             if ratio < min_off_topic_ratio else [])}
    old_data = out.read_bytes() if out.exists() else None  # raw bytes: prior content need not be UTF-8
    old_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    try:
        _write_atomic(out, text)
        _write_atomic(manifest_path, json.dumps(manifest, indent=2))
    except BaseException:
        # Phase-aware rollback covering ALL phases after either file may change (including
        # a directory-fsync failure after EITHER rename). Attempt both restorations
        # independently; a failed rollback leaves mixed state (documented) and never
        # masks the original error.
        if old_data is None:
            try:
                out.unlink(missing_ok=True)  # first build: leave no data without its manifest
            except Exception:
                pass
        else:
            try:
                _write_atomic(out, old_data)  # restore the previous data bytes verbatim
            except Exception:
                pass
        if old_manifest is None:
            try:
                manifest_path.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            try:
                _write_atomic(manifest_path, old_manifest)  # restore the previous manifest bytes verbatim
            except Exception:
                pass
        raise
    return manifest
