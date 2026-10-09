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
    def __init__(self, product: str, path: str | Path):
        if product not in ("atlas", "meemee", "sugarcode"):
            raise ValueError("product must be atlas, meemee or sugarcode")
        self.product = product
        self.path = Path(path)
        self.skipped: list[dict] = []

    def rows(self) -> Iterable[ExampleRow]:
        self.skipped = []
        for n, line in enumerate(self.path.read_text().splitlines(), 1):
            ref = f"{self.path.name}:{n}"
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    raise ValueError("line is not an object")
                call = rec.get("call")
                answers = [] if call is None else [{"name": call["name"], "arguments": call.get("arguments") or {}}]
                row = ExampleRow(query=rec["query"], tools=rec["tools"], answers=answers,
                                 confirmed=rec.get("owner_decision") == "confirmed",
                                 source_ref=str(rec.get("id") or ref), private=bool(rec.get("private", True)),
                                 product=rec.get("product", self.product))
            except (ValueError, KeyError, TypeError) as exc:
                self.skipped.append({"source_ref": ref, "reason": f"unreadable row: {type(exc).__name__}"})
                continue
            yield row
