"""Per-product adapter: an owner-confirmation log (JSONL) -> DomainDataset.

Each line: {"id", "query", "tools", "call": {"name","arguments"} | null,
"owner_decision": "confirmed" | "rejected" | "unreviewed", "private": bool}.
Only ``confirmed`` rows are confirmed training rows. A ``confirmed`` row whose
``call`` is null is an owner-confirmed "no tool applies" row, i.e. a real
off-topic example. Nothing is synthesised and rows never cross products.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .dataset import ExampleRow


class JsonlConfirmationLog:
    """Read UTF-8 JSONL while recording bad rows without their private contents.

    Decode failures are file errors, not row errors. Read the entire file before
    yielding so a later bad byte cannot leave a partially consumed dataset.
    Product tags remain untouched for the downstream product-isolation filter.
    """

    def __init__(self, product: str, path: str | Path):
        if product not in ("atlas", "meemee", "sugarcode"):
            raise ValueError("product must be atlas, meemee or sugarcode")
        self.product = product
        self.path = Path(path)
        self.skipped: list[dict] = []

    def rows(self) -> Iterable[ExampleRow]:
        self.skipped = []
        try:
            text = self.path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            # Do not expose offending bytes, log text, or full paths.
            raise ValueError("confirmation log is not valid UTF-8") from None

        for number, line in enumerate(text.split("\n"), 1):  # NOT splitlines(): U+2028, U+0085, \x0b, \x0c, \x1c-\x1e can sit raw inside a valid JSON string
            ref = f"{self.path.name}:{number}"
            if not line.strip():
                continue
            try:
                record = json.loads(line)
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
            except RecursionError:
                self.skipped.append({"source_ref": ref, "reason": "unreadable row: RecursionError"})
                continue
            except (ValueError, KeyError, TypeError) as exc:
                self.skipped.append({"source_ref": ref, "reason": f"unreadable row: {type(exc).__name__}"})
                continue
            yield row
