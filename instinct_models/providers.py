"""Local/self-hosted model providers and explicitly enabled hosted routes."""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

LOCAL, HOSTED = "local", "hosted"


class ProviderError(RuntimeError):
    pass


class ProviderUnavailable(ProviderError):
    """Not configured or not reachable; the router may try the next route."""


@dataclass
class ChatResult:
    provider: str
    model: str
    text: str
    tool_calls: list[dict]
    raw: dict


Transport = Callable[[str, dict, dict, float], dict]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        raise ProviderError(f"endpoint redirected (HTTP {code}); refusing redirect")


def http_json(url: str, body: dict, headers: dict, timeout: float) -> dict:
    """No redirects and no request, URL, bearer or response bodies in errors."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (ValueError, RecursionError) as exc:
        raise ProviderError("provider returned invalid JSON") from exc
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"provider HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise ProviderUnavailable("provider endpoint unreachable") from None
    except (ValueError, UnicodeError):
        raise ProviderError("provider returned invalid JSON") from None


def _reject_constant(name: str):
    raise ValueError(f"non-finite JSON constant {name}")  # NaN/Infinity are not valid JSON arguments


def _finite_float(text: str) -> float:
    v = float(text)
    if not math.isfinite(v):
        raise ValueError("float literal overflows to infinity")  # e.g. 1e999 parses to inf without calling parse_constant
    return v


def message_text(content) -> str:
    """Plain text of a chat message's content (string, content-parts list, or null)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p["text"] for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


class Provider(ABC):
    name = "provider"
    locality = LOCAL

    def allows_private(self) -> bool:
        """Fail closed unless a concrete provider defines its private trust policy."""
        return False

    @abstractmethod
    def available(self) -> bool:
        """True when this provider is configured and can be called now."""

    @abstractmethod
    def chat(self, messages: list[dict], *, tools: list[dict] | None = None, max_tokens: int = 1024) -> ChatResult:
        """One chat turn; raises ProviderError / ProviderUnavailable on failure."""


def _key_safe_url(url: str) -> bool:
    """A bearer key may only go over https, or over http to a loopback host."""
    try:
        u = urlsplit(url)
        return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"))
    except ValueError:
        return False


class _OpenAICompat(Provider):
    def __init__(self, base_url: str | None, model: str | None, api_key: str | None = None,
                 transport: Transport = http_json, timeout: float = 120, *, trusted_remote: bool = False, allow_cleartext_remote: bool = False):
        self.trusted_remote = trusted_remote
        self.allow_cleartext_remote = allow_cleartext_remote
        self.base_url, self.model, self.api_key, self.transport, self.timeout = (base_url or "").rstrip("/"), model, api_key, transport, timeout

    def allows_private(self) -> bool:
        if self.locality != LOCAL:
            return False
        try:
            if self.trusted_remote:
                u = urlsplit(self.base_url)
                return ((u.scheme == "https" or (u.scheme == "http" and (u.hostname in ("127.0.0.1", "localhost", "::1") or self.allow_cleartext_remote)))
                        and bool(u.hostname)
                        and u.username is None and u.password is None
                        and "?" not in self.base_url and "#" not in self.base_url
                        and (u.port is None or 0 < u.port <= 65535)
                        and not any(ch.isspace() or ord(ch) < 32 for ch in self.base_url))
            require_loopback_url(self.base_url)
            return True
        except (ValueError, ProviderUnavailable):
            return False

    def available(self) -> bool:
        return bool(self.base_url and self.model)

    def chat(self, messages, *, tools=None, max_tokens=1024):
        if not self.available():
            raise ProviderUnavailable(f"{self.name} is not configured")
        body: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        if self.api_key and not _key_safe_url(self.base_url):
            raise ProviderUnavailable(f"{self.name}: refusing to send an API key over plain http to a non-loopback host")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            data = self.transport(f"{self.base_url}/chat/completions", body, headers, self.timeout)
            if not isinstance(data, dict) or not isinstance(data.get("choices"), list):
                raise ValueError()
            msg = data["choices"][0]["message"]
            if not isinstance(msg, dict):
                raise ValueError()
            content = msg.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError()
            raw_calls = msg.get("tool_calls", [])
            if raw_calls is None:
                raw_calls = []
            if not isinstance(raw_calls, list):
                raise ValueError()
            calls = []
            for c in raw_calls:
                fn = c["function"]
                name = fn["name"]
                if not isinstance(name, str) or not name.strip():
                    raise ValueError()
                args = fn["arguments"]
                if not isinstance(args, str):
                    raise ValueError()
                args = json.loads(args, parse_constant=_reject_constant, parse_float=_finite_float)
                if not isinstance(args, dict):
                    raise ValueError()
                calls.append({"name": name, "arguments": args})
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, UnicodeError, RecursionError):
            raise ProviderError("provider returned malformed response or tool call") from None
        return ChatResult(self.name, self.model, content or "", calls, data)



class InklingLocal(_OpenAICompat):
    """Self-hosted Inkling (llama.cpp GGUF / vLLM / SGLang) on her own hardware."""
    name, locality = "inkling-local", LOCAL


class OrnithOpenAICompat(_OpenAICompat):
    """Ornith-1.5 GGUF served locally by llama.cpp or Ollama (OpenAI-compatible /v1)."""
    name, locality = "ornith-local", LOCAL


def require_loopback_url(url: str) -> str:
    """Refuse nonlocal and credential-bearing URLs for privileged/local agent routes."""
    try:
        u = urlsplit(url)
        valid = (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")
                 and u.username is None and u.password is None and u.port is not None
                 and 0 < u.port <= 65535 and "?" not in url and "#" not in url
                 and not any(ch.isspace() or ord(ch) < 32 for ch in url))
    except ValueError:
        valid = False
    if not valid:
        raise ProviderUnavailable("local endpoint must be http on loopback with an explicit port")
    return url.rstrip("/")



class HermesLocal(_OpenAICompat):
    """Hermes open weights served by local Ollama's /v1; not the Hermes Agent CLI."""
    name, locality = "hermes-local", LOCAL

    def available(self) -> bool:
        if not super().available():
            return False
        try:
            self._local_url()
        except ProviderUnavailable:
            return False
        return True

    def _local_url(self) -> str:
        return require_loopback_url(self.base_url)

    def chat(self, messages, *, tools=None, max_tokens=1024):
        self._local_url()
        return super().chat(messages, tools=tools, max_tokens=max_tokens)


def _openclaw_http(url: str, body: dict, headers: dict, timeout: float) -> dict:
    """Refuse redirects and keep privileged payloads out of errors."""
    return http_json(url, body, headers, timeout)



class OpenClawOwner(_OpenAICompat):
    """Explicit owner-only call, NEVER included in automatic Router chains.

    OpenClaw bearer tokens confer full operator rights. The caller must authenticate
    the product user and pass owner_confirmed=True for every invocation. This is not
    a model provider fallback or a public API endpoint.
    """
    name, locality = "openclaw-owner", LOCAL

    def __init__(self, base_url: str, token: str, model: str = "openclaw/default", **kwargs):
        if not isinstance(token, str) or not token.strip():
            raise ProviderUnavailable("OpenClaw owner token required")
        if model != "openclaw/default":
            raise ProviderUnavailable("only the default OpenClaw agent is supported")
        kwargs.setdefault("transport", _openclaw_http)
        super().__init__(require_loopback_url(base_url), model, token, **kwargs)

    def chat(self, messages, *, tools=None, max_tokens=1024, owner_confirmed: bool = False):
        if not owner_confirmed:
            raise ProviderUnavailable("explicit authenticated owner invocation required")
        if tools:
            raise ProviderUnavailable("external tool schemas cannot be sent to OpenClaw owner bridge")
        return super().chat(messages, tools=None, max_tokens=max_tokens)


class InklingHFRouter(_OpenAICompat):
    """Inkling through the Hugging Face router with her HF_TOKEN. Hosted: never used for private tasks."""
    name, locality = "inkling-hf-router", HOSTED

    def __init__(self, model: str, token: str | None = None, transport: Transport = http_json, timeout: float = 120):
        super().__init__("https://router.huggingface.co/v1", model, token if token is not None else os.environ.get("HF_TOKEN"),
                         transport, timeout)

    def available(self) -> bool:
        return bool(self.model and self.api_key)


# The pinned needle3 revision publishes engine 3.0.2. Do not silently downgrade.
# An operator may explicitly select another engine via INSTINCT_NEEDLE_ENGINE_V3.

def fix_needle_engine(fetch_module: Any, env: dict | None = None) -> str | None:
    """Apply an explicit engine override; otherwise retain the upstream engine pin."""
    e = os.environ if env is None else env
    versions = getattr(fetch_module, "ENGINE_VERSIONS", None)
    if not isinstance(versions, dict):
        return None
    current = versions.get(3)
    target = e.get("INSTINCT_NEEDLE_ENGINE_V3")
    if target and target != current:
        versions[3] = target
    return versions.get(3)


def needle_with_fallback(needle_cls: Callable[..., Any]) -> Callable[..., Any]:
    """Construct Needle 3; if the engine cannot be fetched or loaded, fall back to Needle 2 (engine 2.0.4).

    Only for the base model: tuned weights carry their own generation, so errors there propagate.
    """
    def make(**kwargs: Any) -> Any:
        if kwargs.get("weights") or "generation" in kwargs:
            return needle_cls(**kwargs)
        try:
            return needle_cls(**kwargs)
        except Exception as first:  # noqa: BLE001 - HF 404s, missing libs and load errors all mean "try v2"
            try:
                return needle_cls(generation=2, **kwargs)
            except Exception as second:
                raise ProviderUnavailable("Needle 3 and Needle 2 fallback could not load") from None
    return make


class NeedleLocal(Provider):
    """On-device Needle (pip cactus-needle). Tool selection + argument extraction only:
    short inputs (256-token window at inference), no free-form generation."""
    name, locality = "needle-local", LOCAL

    def __init__(self, weights: str | None = None, factory: Callable[..., Any] | None = None, min_confidence: float = 0.8,
                 telemetry: bool = False):
        self.weights, self.factory, self.min_confidence = weights, factory, min_confidence
        # cactus-needle sends anonymous usage counts to its developers by default. Off unless opted in.
        self.telemetry = telemetry

    def allows_private(self) -> bool:
        return not self.telemetry

    def _factory(self):
        if self.factory:
            return self.factory
        if not self.telemetry:
            # Verified in cactus-needle 3.0.5: needle/_telemetry.py checks NEEDLE_TELEMETRY == "0" and DO_NOT_TRACK;
            # its package README says the engine binary needs both NEEDLE_TELEMETRY=0 and DO_NOT_TRACK=1.
            os.environ["NEEDLE_TELEMETRY"] = "0"
            os.environ["DO_NOT_TRACK"] = "1"
        try:
            import needle  # type: ignore  # pip install cactus-needle; import does not load JAX
        except ImportError as exc:
            raise ProviderUnavailable("cactus-needle is not installed (pip install cactus-needle)") from exc
        try:
            from needle.agent import fetch as needle_fetch  # type: ignore
            fix_needle_engine(needle_fetch)
        except ImportError:
            pass
        return needle_with_fallback(needle.Needle)

    def available(self) -> bool:
        try:
            self._factory()
            return True
        except ProviderUnavailable:
            return False

    def chat(self, messages, *, tools=None, max_tokens=256):
        """One turn via ``agent.complete`` (documented API). Returns calls only when
        the model called a tool; tuned weights report no calibrated confidence, so the
        threshold applies to the base model only."""
        if not tools:
            raise ProviderUnavailable("Needle only handles tool-calling turns")
        msgs = [m for m in messages if isinstance(m, dict)]
        query = message_text(next((m.get("content") for m in reversed(msgs) if m.get("role") == "user"), ""))
        system = message_text(next((m.get("content") for m in msgs if m.get("role") == "system"), None)) or None
        kwargs: dict[str, Any] = {"tools": tools}
        if self.weights:
            kwargs["weights"] = self.weights
        if system:
            kwargs["system"] = system
        agent = self._factory()(**kwargs)
        out = agent.complete(query, max_new_tokens=min(max_tokens, 256))
        if not isinstance(out, dict) or not out.get("success", True):
            raise ProviderError("Needle inference failed") from None
        calls = out.get("function_calls", []) if out.get("type") == "call" else []
        if not isinstance(calls, list) or any(
            not isinstance(c, dict) or not isinstance(c.get("name"), str)
            or not c["name"].strip() or not isinstance(c.get("arguments"), dict)
            for c in calls
        ):
            raise ProviderError("Needle returned malformed tool calls") from None
        validation = out.get("validation") or {}
        if not isinstance(validation, dict):
            raise ProviderError("Needle returned malformed validation") from None
        conf = out.get("confidence")
        if calls and not self.weights and isinstance(conf, (int, float)) and not conf >= self.min_confidence:  # NaN fails >=, so it escalates too
            calls = []  # low confidence: let the router escalate
        # validation.ungrounded is written by needle/__init__.py _annotate_ungrounded (cactus-needle 3.0.5).
        if calls and validation.get("ungrounded"):
            calls = []  # Needle flagged argument values not found in the query: escalate instead of trusting them
        return ChatResult(self.name, self.weights or "needle-base", "", calls, out)

# --- Jev (TypeSafe AI System One evaluation model) ---------------------------------

JEV_GATEWAY_ENDPOINT = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
JEV_DIRECT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_QUESTION_TYPES = ("noul", "choice", "score")


class JevStatusError(ProviderError):
    """The Jev API answered with a non-2xx status."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"Jev API HTTP {status}: {detail[:300]}")
        self.status = status


class _NoTransportRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so credentials and request data stay at the chosen endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _jev_http(url: str, body: dict, headers: dict, timeout: float) -> dict:
    """Default Jev transport. Same signature as http_json, but keeps the HTTP status so
    the caller can retry 429/529 and explain 401/422 precisely."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.build_opener(_NoTransportRedirect()).open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (ValueError, RecursionError) as exc:
        raise ProviderError("provider returned invalid JSON") from exc
    except urllib.error.HTTPError as exc:
        raise JevStatusError(exc.code, exc.read()[:300].decode("utf-8", "replace")) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise ProviderUnavailable(f"cannot reach {url}: {exc}") from exc


def validate_questions(questions: dict) -> dict:
    """Check a Jev question map against the shapes documented at https://docs.typesafe.ai/api.
    Returns the map unchanged; raises ProviderError on the first violation."""
    if not isinstance(questions, dict) or not questions:
        raise ProviderError("questions must be a non-empty map of question id -> question")
    for qid, q in questions.items():
        if not isinstance(q, dict):
            raise ProviderError(f"question {qid!r} must be an object")
        qtype = q.get("type")
        if qtype not in JEV_QUESTION_TYPES:
            raise ProviderError(f"question {qid!r}: type must be one of {JEV_QUESTION_TYPES}")
        if "instructions" not in q:
            raise ProviderError(f"question {qid!r}: instructions are required")
        criteria = q.get("criteria")
        if qtype == "choice":
            if not isinstance(criteria, dict) or not criteria:
                raise ProviderError(f"choice question {qid!r}: criteria must map options to descriptions")
            if len(criteria) > 255:
                raise ProviderError(f"choice question {qid!r}: at most 255 options")
        elif qtype == "score":
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
                raise ProviderError(f"score question {qid!r}: criteria must be an ordered list of 2-10 levels")
        elif criteria is not None and not isinstance(criteria, dict):
            raise ProviderError(f"noul question {qid!r}: criteria, when present, must be an object with true/false keys")
    return questions


class JevEval(Provider):
    """TypeSafe AI's Jev - a "System One" evaluation model (https://typesafe.ai).

    NOT a chat model: it takes one state plus typed questions (choice / score / noul) and
    returns structured decisions with probabilities, so it never joins the chat Router
    chain; call ``evaluate()`` directly. Hosted and key-gated (paid credits, no free tier
    as of 2026-09-26): ``available()`` is False without a key, so it is OFF by default.
    Gateway is the first configured route (AI_GATEWAY_API_KEY or INSTINCT_AI_GATEWAY_API_KEY).
    The official TypeSafe direct API is the alternate (JEV_API_KEY or INSTINCT_JEV_API_KEY).
    Both are hosted, paid routes; never send private state to them.
    """
    name, locality = "jev", HOSTED

    def __init__(self, api_key: str | None = None, model: str = "jev-latest",
                 transport: Transport = _jev_http, timeout: float = 60,
                 max_retries: int = 3, sleeper: Callable[[float], None] = time.sleep,
                 gateway_api_key: str | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("JEV_API_KEY")
        self.gateway_api_key = (gateway_api_key if gateway_api_key is not None else
                                os.environ.get("INSTINCT_AI_GATEWAY_API_KEY") or os.environ.get("AI_GATEWAY_API_KEY"))
        self.model, self.transport, self.timeout = model, transport, timeout
        self.max_retries, self.sleeper = max_retries, sleeper

    def available(self) -> bool:
        return bool(self.gateway_api_key or self.api_key)

    def chat(self, messages, *, tools=None, max_tokens=1024) -> ChatResult:
        raise ProviderUnavailable("jev is an evaluation model, not a chat model; use evaluate()")

    def evaluate(self, state, questions: dict, *, model: str | None = None) -> dict:
        """Evaluate ``state`` (str | object | array of str) against typed ``questions``.
        Returns {"model", "answers", "usage", "raw"}. Retries 429/529 with exponential
        backoff per the Jev docs; 401 means the key is missing or invalid."""
        if not self.available():
            raise ProviderUnavailable(
                "jev is not configured: set AI_GATEWAY_API_KEY or JEV_API_KEY (both are paid routes)")
        gateway = bool(self.gateway_api_key)
        endpoint = JEV_GATEWAY_ENDPOINT if gateway else JEV_DIRECT_ENDPOINT
        key = self.gateway_api_key if gateway else self.api_key
        selected_model = model or ("typesafe-ai/jev" if gateway else self.model)
        body = {"state": state, "model": selected_model, "questions": validate_questions(questions)}
        headers = {"Authorization": f"Bearer {key}"}
        attempt = 0
        while True:
            try:
                data = self.transport(endpoint, body, headers, self.timeout)
                break
            except JevStatusError as exc:
                if exc.status in (429, 529) and attempt < self.max_retries:
                    self.sleeper(float(2 ** attempt))
                    attempt += 1
                    continue
                if exc.status == 401:
                    raise ProviderError("jev: API key missing or invalid (401); check " + ("AI_GATEWAY_API_KEY" if gateway else "JEV_API_KEY")) from exc
                raise
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise ProviderError("jev: unexpected response shape (no 'answers' object)")
        return {"model": data.get("model", selected_model), "answers": data["answers"],
                "usage": data.get("usage") or {}, "raw": data}
