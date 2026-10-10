"""Per-product adapter: an owner-confirmation log (JSONL) -> DomainDataset.

Each line: {"id", "query", "tools", "call": {"name","arguments"} | null,
"owner_decision": "confirmed" | "rejected" | "unreviewed", "private": bool}.
Only ``confirmed`` rows are confirmed training rows. A ``confirmed`` row whose
``call`` is null is an owner-confirmed "no tool applies" row, i.e. a real
off-topic example. Nothing is synthesised and rows never cross products.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Iterable

from .dataset import ExampleRow


DEFAULT_MAX_BYTES = 256 * 1024 * 1024


class _NonFinite(ValueError):
    pass


def _reject_constant(name: str):
    raise _NonFinite(name)


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):  # e.g. 1e999 parses to inf without calling parse_constant
        raise _NonFinite(text)
    return value


def _looks_like_utf16(raw: bytes) -> bool:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return True
    head = raw[:64]
    return len(head) >= 4 and (set(head[1::2]) == {0} or set(head[0::2]) == {0})  # NUL-interleaved ASCII, no BOM


class JsonlConfirmationLog:
    """Read UTF-8 JSONL while recording bad rows without their private contents.

    Decode failures are file errors, not row errors. Read the entire file before
    yielding so a later bad byte cannot leave a partially consumed dataset.
    Product tags remain untouched for the downstream product-isolation filter.
    """

    def __init__(self, product: str, path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES):
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise ValueError("max_bytes must be a positive integer")
        if product not in ("atlas", "meemee", "sugarcode"):
            raise ValueError("product must be atlas, meemee or sugarcode")
        self.product = product
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.skipped: list[dict] = []
        self.warnings: list[dict] = []

    def rows(self) -> Iterable[ExampleRow]:
        self.skipped = []
        self.warnings = []
        with open(self.path, "rb") as f:  # size is checked on the OPEN descriptor, and the read itself is bounded
            if os.fstat(f.fileno()).st_size > self.max_bytes:
                raise ValueError(f"confirmation log is larger than the {self.max_bytes}-byte limit")
            raw = f.read(self.max_bytes + 1)
        if len(raw) > self.max_bytes:
            raise ValueError(f"confirmation log is larger than the {self.max_bytes}-byte limit")
        if _looks_like_utf16(raw):
            raise ValueError("confirmation log looks like UTF-16 (PowerShell '>' writes this); re-save it as UTF-8")
        try:
            text = raw.decode("utf-8-sig", errors="strict")  # utf-8-sig strips ONE leading BOM (else it breaks row 1); decoding stays strict
        except UnicodeDecodeError:
            # Do not expose offending bytes, log text, or full paths.
            raise ValueError("confirmation log is not valid UTF-8") from None

        seen_ids: dict = {}
        for number, line in enumerate(text.split("\n"), 1):  # NOT splitlines(): U+2028, U+0085, \x0b, \x0c, \x1c-\x1e can sit raw inside a valid JSON string
            ref = f"{self.path.name}:{number}"
            if not line.strip():
                continue
            try:
                record = json.loads(line, parse_constant=_reject_constant, parse_float=_finite_float)
                if not isinstance(record, dict):
                    raise ValueError("line is not an object")
                tools = record["tools"]
                if not isinstance(tools, list):
                    self.skipped.append({"source_ref": ref, "reason": "tools must be a list"})
                    continue
                call = record.get("call")
                if call is None:
                    answers = []
                else:
                    if not isinstance(call, dict):
                        self.skipped.append({"source_ref": ref, "reason": "call must be an object or null"})
                        continue
                    arguments = call.get("arguments", {})
                    if arguments is None:
                        arguments = {}  # explicit null means no arguments, as the legacy reader and the dataset builder treat it
                    if not isinstance(arguments, dict):
                        self.skipped.append({"source_ref": ref, "reason": "arguments must be an object"})
                        continue
                    answers = [{"name": call["name"], "arguments": arguments}]
                row = ExampleRow(
                    query=record["query"],
                    tools=tools,
                    answers=answers,
                    confirmed=record.get("owner_decision") == "confirmed",
                    source_ref=str(record.get("id") or ref),
                    private=bool(record.get("private", True)),
                    product=record.get("product", self.product),
                )
            except _NonFinite:
                self.skipped.append({"source_ref": ref, "reason": "non-finite number (NaN or Infinity)"})
                continue
            except RecursionError:
                self.skipped.append({"source_ref": ref, "reason": "unreadable row: RecursionError"})
                continue
            except (ValueError, KeyError, TypeError) as exc:
                self.skipped.append({"source_ref": ref, "reason": f"unreadable row: {type(exc).__name__}"})
                continue
            rid = record.get("id")
            if isinstance(rid, (str, int)) and not isinstance(rid, bool) and rid != "":
                if rid in seen_ids:
                    self.warnings.append({"source_ref": ref, "reason": f"duplicate id, first seen at line {seen_ids[rid]}"})
                else:
                    seen_ids[rid] = number
            yield row
