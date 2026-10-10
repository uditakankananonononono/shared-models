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


def _write_atomic(path: Path, text: str) -> None:
    """Write via a fresh temp file in the same directory, then rename over the target (never a partial file at the target)."""
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
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
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
    if out.parent.is_symlink():
        raise ValueError("refusing to write into a symlinked output directory")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except (NotADirectoryError, FileExistsError) as exc:
        raise ValueError("output directory path is blocked by a file") from exc
    _check_output_target(out)  # both targets are checked before anything is written
    _check_output_target(manifest_path)
    text = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in kept)
    _write_atomic(out, text)
    manifest = {"product": dataset.product, "rows": len(kept), "dropped": len(dropped), "dropped_detail": dropped[:200],
                "off_topic_ratio": round(ratio, 3), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "train_locally_only": private, "path": str(out),
                "warnings": ([f"off-topic ratio {ratio:.2f} is below {min_off_topic_ratio}; the tuned model may call tools on everything"]
                             if ratio < min_off_topic_ratio else [])}
    _write_atomic(manifest_path, json.dumps(manifest, indent=2))
    return manifest
