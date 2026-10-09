"""Measure the lexical floor on held-out rows instead of assuming it works."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

from ..lexical import LexicalToolModel


def _load_rows(jsonl_path) -> list[dict]:
    """Read and validate rows; any problem is a ValueError naming the file line."""
    rows = []
    for n, line in enumerate(Path(jsonl_path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except (ValueError, RecursionError) as exc:
            raise ValueError(f"line {n}: not valid JSON") from exc
        try:
            LexicalToolModel._check_row(n, r)
        except ValueError as exc:
            raise ValueError(f"line {n}: {str(exc).split(': ', 1)[-1]}") from None
        if "tools" not in r or "answers" not in r:
            raise ValueError(f"line {n}: row needs 'tools' and 'answers'")
        rows.append(r)
    return rows


def evaluate_lexical(jsonl_path: str | Path, *, holdout_percent: int = 25, **model_kw) -> dict:
    """Deterministic hold-out split by query hash; reports exact-call accuracy and abstention.

    A tool-call row counts correct only if name and every argument match.
    An off-topic row counts correct only if the model abstains.
    """
    if not 1 <= holdout_percent <= 50:
        raise ValueError("holdout_percent must be 1..50")
    rows = _load_rows(jsonl_path)
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


def calibration_sweep(jsonl_path: str | Path, *, holdout_percent: int = 25,
                      thresholds=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)) -> dict:
    """For each min_confidence, how many held-out calls would be served right, served wrong, or abstained.

    Naive Bayes confidences are usually too high, so the right threshold has to
    come from a product's own held-out rows. This reports the trade-off; it does
    not pick one. "abstained" is split into correct off-topic abstentions and
    missed calls (lost recall). Thresholds compared on the same held-out rows
    are optimistic: confirm any chosen value on a separate confirmation set.
    Served-wrong counts a wrong tool, wrong arguments, or any call
    on an off-topic row.
    """
    rows = _load_rows(jsonl_path)
    train = [r for r in rows if zlib.crc32(r["query"].encode()) % 100 >= holdout_percent]
    test = [r for r in rows if zlib.crc32(r["query"].encode()) % 100 < holdout_percent]
    if not train or not test:
        raise ValueError("split left an empty side; need more rows")
    out = []
    for t in thresholds:
        model = LexicalToolModel(min_confidence=t).fit(train)
        right = wrong = abstain = off_abstain = missed = 0
        for r in test:
            pred = model.predict(r["query"], r["tools"])
            if pred is None:
                abstain += 1
                if r["answers"]:
                    missed += 1
                else:
                    off_abstain += 1
                continue
            want = r["answers"][0] if r["answers"] else None
            ok = want is not None and pred["name"] == want["name"] and pred["arguments"] == (want.get("arguments") or {})
            right += ok
            wrong += not ok
        out.append({"min_confidence": t, "served_right": right, "served_wrong": wrong, "abstained": abstain,
                    "abstained_off_topic_correct": off_abstain, "abstained_missed_call": missed})
    return {"test_rows": len(test), "train_rows": len(train), "sweep": out}
