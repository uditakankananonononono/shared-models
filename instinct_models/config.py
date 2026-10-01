"""Per-product configuration from env, optionally overlaid by a small YAML/JSON file.

Env (prefix INSTINCT_):
  INSTINCT_PRODUCT             atlas | meemee | sugarcode (required)
  INSTINCT_INKLING_LOCAL_URL   OpenAI-compatible base URL for self-hosted Inkling (llama.cpp/vLLM/SGLang)
  INSTINCT_INKLING_LOCAL_MODEL model name served there (default inkling-small)
  INSTINCT_HF_MODEL            HF router model id (default thinkingmachines/Inkling-Small); token from HF_TOKEN
  INSTINCT_ORNITH_URL          OpenAI-compatible base URL (Ollama: http://localhost:11434/v1)
  INSTINCT_ORNITH_MODEL        model tag as pulled locally (no default: must match what she pulled)
  INSTINCT_NEEDLE_WEIGHTS      path to a product .cact (tuned) - empty means the base Needle model
  INSTINCT_ALLOW_HOSTED        1 to allow metered hosted HF router for non-private tasks (default 0)
  INSTINCT_TRUST_REMOTE        1 explicitly trusts configured Ornith/Inkling remote endpoints for private tasks
  INSTINCT_JEV_API_KEY         TypeSafe AI direct evaluation API key (optional; falls back to JEV_API_KEY).
  INSTINCT_AI_GATEWAY_API_KEY  Vercel AI Gateway key for Jev (optional; falls back to AI_GATEWAY_API_KEY).
  INSTINCT_LEXICAL_TRAIN_JSONL Needle-format JSONL (from build_needle_jsonl) to train the built-in lexical tool model
  INSTINCT_HERMES_URL         local Ollama OpenAI-compatible /v1 URL (opt-in)
  INSTINCT_HERMES_MODEL       pulled Hermes tag, e.g. hermes3:3b
                               Jev is hosted and key-gated (paid credits); empty keeps it OFF.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

PRODUCTS = ("atlas", "meemee", "sugarcode")


@dataclass(frozen=True)
class ProductConfig:
    product: str
    inkling_local_url: str | None = None
    inkling_local_model: str = "inkling-small"
    hf_model: str = "thinkingmachines/Inkling-Small"
    ornith_url: str | None = None
    ornith_model: str | None = None
    needle_weights: str | None = None
    lexical_train_jsonl: str | None = None
    hermes_url: str | None = None
    hermes_model: str | None = None
    allow_hosted: bool = False
    trust_remote: bool = False
    jev_api_key: str | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.product not in PRODUCTS:
            raise ValueError(f"product must be one of {PRODUCTS}, got {self.product!r}")


_TRUE, _FALSE = ("1", "true", "yes", "on"), ("0", "false", "no", "off", "")


_STR_FIELDS = {"inkling_local_url", "inkling_local_model", "hf_model", "ornith_url", "ornith_model", "needle_weights",
               "lexical_train_jsonl", "hermes_url", "hermes_model", "jev_api_key"}


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.strip().lower() in _TRUE + _FALSE:
        return v.strip().lower() in _TRUE
    raise ValueError(f"allow_hosted must be true or false, got {v!r}")


def _load_file(path: str) -> dict:
    text = Path(path).read_text()
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # optional
        except ImportError as exc:
            raise ValueError("YAML config needs PyYAML; use JSON instead") from exc
        return yaml.safe_load(text) or {}
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"{path}: not valid JSON") from exc
    return data


def load_config(env: dict | None = None, path: str | None = None) -> ProductConfig:
    e = os.environ if env is None else env
    g = lambda k, d=None: (e.get(f"INSTINCT_{k}") or d)
    cfg = ProductConfig(product=g("PRODUCT", ""), inkling_local_url=g("INKLING_LOCAL_URL"),
                        inkling_local_model=g("INKLING_LOCAL_MODEL", "inkling-small"),
                        hf_model=g("HF_MODEL", "thinkingmachines/Inkling-Small"), ornith_url=g("ORNITH_URL"),
                        ornith_model=g("ORNITH_MODEL"), needle_weights=g("NEEDLE_WEIGHTS"), hermes_url=g("HERMES_URL"), lexical_train_jsonl=g("LEXICAL_TRAIN_JSONL"),
                        hermes_model=g("HERMES_MODEL"),
                        trust_remote=g("TRUST_REMOTE", "0").strip().lower() in ("1", "true", "yes", "on"),
                        allow_hosted=g("ALLOW_HOSTED", "0").strip().lower() in ("1", "true", "yes", "on"),
                        jev_api_key=g("JEV_API_KEY") or e.get("JEV_API_KEY") or None)
    if path:
        data = _load_file(path)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: config file must contain an object")
        if "product" in data and data["product"] != cfg.product:
            raise ValueError("config file cannot change the product set by INSTINCT_PRODUCT")
        for k, v in data.items():
            if k in _STR_FIELDS and v is not None and not isinstance(v, str):
                raise ValueError(f"{k} must be a string or null, got {type(v).__name__}")
        if "allow_hosted" in data:
            data = {**data, "allow_hosted": _as_bool(data["allow_hosted"])}
        known = {k: v for k, v in data.items() if k in ProductConfig.__dataclass_fields__ and k != "extra"}
        cfg = replace(cfg, **known, extra={k: v for k, v in data.items() if k not in known})
    return cfg
