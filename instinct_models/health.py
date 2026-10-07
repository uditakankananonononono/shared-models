"""Zero-token health probes for the shared providers.

`probe(base_url, model, api_key)` does GET {base_url}/models and reports whether
the model is listed. On the Hugging Face router the model list is public, so a
separate whoami call checks that HF_TOKEN is actually valid. Redirects are
refused, including same-origin redirects; configure the final endpoint directly.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import urllib.parse


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never send a health credential beyond the explicitly configured URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get(url: str, api_key: str | None, timeout: float) -> dict:
    h = {"User-Agent": "instinct-models"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return json.loads(r.read().decode())


def hf_token_valid(token: str | None, timeout: float = 15) -> bool | str:
    if not token:
        return False
    try:
        data = _get("https://huggingface.co/api/whoami-v2", token, timeout)
        return isinstance(data, dict) and isinstance(data.get("name"), str) and bool(data["name"])
    except urllib.error.HTTPError as e:
        return False if e.code in (401, 403) else f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return f"unreachable: {getattr(e, 'reason', e)}"


def probe(base_url: str, model: str | None, api_key: str | None = None, timeout: float = 15) -> dict:
    """Never raises. ok=True means the server answered (and, on HF, the token is valid)."""
    try:
        data = _get(base_url.rstrip("/") + "/models", api_key, timeout)
    except urllib.error.HTTPError as e:
        return {"base_url": base_url, "ok": False, "error": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return {"base_url": base_url, "ok": False, "error": str(getattr(e, "reason", e))}
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return {"base_url": base_url, "ok": False, "error": "invalid model-list response"}
    if any(not isinstance(m, dict) or not isinstance(m.get("id"), str) for m in data["data"]):
        return {"base_url": base_url, "ok": False, "error": "invalid model-list entry"}
    ids = [m["id"] for m in data["data"]]
    out = {"base_url": base_url, "ok": True, "model": model, "model_listed": model in ids,
           "models_available": len(ids)}
    if urllib.parse.urlsplit(base_url).hostname == "router.huggingface.co":
        out["token_valid"] = hf_token_valid(api_key, timeout)
        out["ok"] = out["token_valid"] is True
    return out
