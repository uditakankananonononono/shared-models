"""LoRA fine-tune of Needle on a product dataset, using the documented CLI:

    needle finetune data.jsonl --epochs N --out adapter.pkl
    needle build checkpoints/needle2.pkl --lora adapter.pkl --out tuned.cact

Runs locally (JAX on CPU/GPU/Metal). Never uploads: ``--upload`` is not passed and
NEEDLE_HF_REPO is removed from the child env. The adapter registry records dataset
hash, command, and output hash so a product can pin exactly what it serves.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

Runner = Callable[[list[str], dict], subprocess.CompletedProcess]


def _run(cmd: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=6 * 3600)


@dataclass
class NeedleLoRAJob:
    product: str
    dataset_jsonl: str
    out_dir: str
    base_checkpoint: str = "checkpoints/needle2.pkl"
    epochs: int = 10
    val_split: float = 0.1


class RegistryTornError(ValueError):
    """A final no-LF registry line with malformed or incomplete JSON: consistent with an interrupted append, cause not proven."""


def _refuse(fd: int, reg: Path):
    os.close(fd)
    raise ValueError(f"{reg}: training registry must be a regular non-symlink file")


def read_registry(out_dir) -> list[dict]:
    """Parse ``<out_dir>/registry.jsonl`` into its records, oldest first. A missing file is an empty registry.

    Lines split on LF only (U+2028 and friends inside a JSON string are not boundaries); one UTF-8 BOM at the start is
    ignored; blank lines are skipped. A corrupt line that is followed by more data raises ValueError naming the file and
    1-based line number. A final line with no LF whose JSON is incomplete or malformed raises RegistryTornError (consistent with an
    interrupted append, though a missing LF alone does not prove a crash; it is reported, never treated as a record); a final line with no LF that parses is returned as a record.
    Each record must be a JSON object. Nothing is verified about the files a record points at: compare
    ``tuned_sha256`` with the file on disk yourself.
    """
    reg = Path(out_dir) / "registry.jsonl"
    # Same discipline as the writer: open the leaf without following a symlink or blocking on a FIFO, then check the
    # OPEN descriptor and read from it, so a swap between a check and the read cannot redirect us to another file.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(reg, flags)
    except FileNotFoundError:
        return []
    except OSError as exc:  # ELOOP for a symlink, plus permission and other errors
        raise ValueError(f"{reg}: training registry must be a readable regular non-symlink file ({exc.strerror})") from exc
    with os.fdopen(fd, "rb", closefd=True) if stat.S_ISREG(os.fstat(fd).st_mode) else _refuse(fd, reg) as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{reg}: registry is not valid UTF-8") from exc
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    records: list[dict] = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        last = n == len(lines)  # no LF after it
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            if last:
                raise RegistryTornError(f"{reg}: line {n} has no trailing newline and is incomplete or malformed JSON") from exc
            raise ValueError(f"{reg}: line {n} is not a valid registry record: {exc}") from exc
        except RecursionError as exc:
            raise ValueError(f"{reg}: line {n} is not a valid registry record: nested too deeply") from exc
        if not isinstance(rec, dict):  # valid JSON, wrong shape: an ordinary error, not a torn append
            raise ValueError(f"{reg}: line {n} is not a valid registry record: not a JSON object")
        records.append(rec)
    return records


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def train_needle_lora(job: NeedleLoRAJob, runner: Runner = _run, cli: str = "needle") -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", job.product or ""):
        raise ValueError(f"invalid product name {job.product!r}")
    if isinstance(job.epochs, bool) or not isinstance(job.epochs, int) or job.epochs < 1:
        raise ValueError("epochs must be a positive integer")
    if isinstance(job.val_split, bool) or not isinstance(job.val_split, (int, float)) or not 0 <= job.val_split < 1:
        raise ValueError("val_split must be a number in [0, 1)")  # also rejects NaN
    if not isinstance(job.base_checkpoint, str) or not job.base_checkpoint or job.base_checkpoint.startswith("-"):
        raise ValueError("base_checkpoint must be a path, not an option")
    data = Path(job.dataset_jsonl)
    if not data.is_file():
        raise FileNotFoundError(job.dataset_jsonl)
    manifest_path = Path(str(data) + ".manifest.json")
    try:
        ds_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    except (ValueError, RecursionError) as exc:
        raise ValueError("dataset manifest is not valid JSON; rebuild it") from exc
    if not isinstance(ds_manifest, dict):
        raise ValueError("dataset manifest must be a JSON object; rebuild it")
    if ds_manifest and ds_manifest.get("sha256") != _sha(data):
        raise ValueError("dataset changed since its manifest was written; rebuild it")
    if runner is _run and shutil.which(cli) is None:
        raise RuntimeError("needle CLI not found; pip install cactus-needle")
    out = Path(job.out_dir)
    if out.is_symlink():
        raise ValueError("training output directory must not be a symlink")
    out.mkdir(parents=True, exist_ok=True)
    reg = out / "registry.jsonl"
    if reg.is_symlink() or (reg.exists() and not reg.is_file()):
        raise ValueError("training registry must be a regular non-symlink file")
    adapter, tuned = out / f"{job.product}-adapter.pkl", out / f"{job.product}-tuned.cact"
    for stale in (adapter, tuned):  # a leftover file must not pass for this run's output
        stale.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("NEEDLE_HF_REPO", "OPENROUTER_API_KEY")}
    steps = [[cli, "finetune", str(data), "--epochs", str(job.epochs), "--val-split", str(job.val_split), "--out", str(adapter)],
             [cli, "build", job.base_checkpoint, "--lora", str(adapter), "--out", str(tuned)]]
    logs = []
    for cmd in steps:
        res = runner(cmd, env)
        logs.append({"cmd": cmd, "returncode": res.returncode, "stdout_tail": (res.stdout or "")[-2000:],
                     "stderr_tail": (res.stderr or "")[-2000:]})
        if res.returncode != 0:
            raise RuntimeError(f"{cmd[1]} failed (exit {res.returncode}): {(res.stderr or '')[-500:]}")
    if not tuned.is_file():
        raise RuntimeError("needle build reported success but no .cact was written")
    record = {"product": job.product, "dataset_sha256": _sha(data), "dataset_rows": ds_manifest.get("rows"),
              "train_locally_only": ds_manifest.get("train_locally_only", True), "adapter": str(adapter),
              "tuned_weights": str(tuned), "tuned_sha256": _sha(tuned), "epochs": job.epochs,
              "trained_at": datetime.now(timezone.utc).isoformat(), "logs": logs}
    if reg.is_symlink():raise ValueError("training registry symlink refused")
    fd = os.open(reg, os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
    with os.fdopen(fd, "a+", encoding="utf-8") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("training registry must be regular")
        size = os.fstat(f.fileno()).st_size
        lead = "\n" if size and os.pread(f.fileno(), 1, size - 1) != b"\n" else ""  # heal a missing final LF
        f.write(lead + json.dumps(record) + "\n")
    return record
