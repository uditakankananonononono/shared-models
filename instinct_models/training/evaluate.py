"""Measure the lexical floor on held-out rows instead of assuming it works."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

from ..lexical import LexicalToolModel


def evaluate_lexical(jsonl_path: str | Path, *, holdout_percent: int = 25, **model_kw) -> dict:
    """Deterministic hold-out split by query hash; reports exact-call accuracy and abstention.

    A tool-call row counts correct only if name and every argument match.
    An off-topic row counts correct only if the model abstains.
    """
    if not 1 <= holdout_percent <= 50:
        raise ValueError("holdout_percent must be 1..50")
    rows = [json.loads(l) for l in Path(jsonl_path).read_text().splitlines() if l.strip()]
    train, test = [], []
    for r in rows:
        (test if zlib.crc32(r["query"].encode()) % 100 < holdout_percent else train).append(r)
    if not train or not test:
        raise ValueError("split left an empty side; need more rows")
    model = LexicalToolModel(**model_kw).fit(train)
    call_ok = call_n = off_ok = off_n = wrong_call = 0
    for r in test:
        pred = model.predict(r["query"], r["tools"])
        if r["answers"]:
            call_n += 1
            want = r["answers"][0]
            if pred and pred["name"] == want["name"] and pred["arguments"] == (want.get("arguments") or {}):
                call_ok += 1
            elif pred:
                wrong_call += 1
        else:
            off_n += 1
            off_ok += pred is None
    return {"train_rows": len(train), "test_rows": len(test),
            "call_rows": call_n, "call_exact": call_ok, "call_wrong_confident": wrong_call,
            "call_abstained": call_n - call_ok - wrong_call,
            "off_topic_rows": off_n, "off_topic_abstained": off_ok}
