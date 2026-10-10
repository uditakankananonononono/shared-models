"""Compatibility aliases. The hardening prepared for SM-U-B now lives in providers.py.

HardenedJevStatusError is JevStatusError; hardened_jev_transport is the default _jev_http;
JevEval.evaluate validates questions, state and usage itself, so guarded_evaluate just calls it.
"""
from .providers import (JevStatusError as HardenedJevStatusError, _jev_http as hardened_jev_transport,
                        _jev_opener, _NoTransportRedirect, validate_jev_questions_strict,
                        validate_state, validate_usage)


def parse_jev_response(data, selected_model: str) -> dict:
    from .providers import ProviderError
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise ProviderError("jev: unexpected response shape (no 'answers' object)")
    return {"model": data.get("model", selected_model), "answers": data["answers"],
            "usage": validate_usage(data.get("usage")), "raw": data}


def guarded_evaluate(jev, state, questions, *, model=None):
    return jev.evaluate(state, questions, model=model)


__all__ = ["HardenedJevStatusError", "guarded_evaluate", "hardened_jev_transport", "parse_jev_response",
           "validate_jev_questions_strict", "validate_state", "validate_usage"]
