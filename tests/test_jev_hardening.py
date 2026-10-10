"""Tests for instinct_models.jev_hardening (unit SM-U-B-JEV-HARDENING).

Authored by the peer as prep, run and amended by the integrator (the hardening is now in providers.py). Fake transports and fake openers only; no network, no live
or hosted calls, no credentials.
"""
import io
import json
import unittest
import urllib.error
import urllib.request
from unittest import mock

from instinct_models.jev_hardening import (
    HardenedJevStatusError,
    guarded_evaluate,
    hardened_jev_transport,
    parse_jev_response,
    validate_jev_questions_strict,
    validate_state,
    validate_usage,
    _jev_opener,
    _NoTransportRedirect,
)
from instinct_models.providers import JevEval, JevStatusError, ProviderError, ProviderUnavailable


SECRET_BODY = b'{"error":{"message":"secret upstream detail abc123"}}'

VALID_QUESTIONS = {
    "q1": {"type": "choice", "instructions": "pick one", "criteria": {"a": "option a", "b": "option b"}},
    "q2": {"type": "score", "instructions": "rate it", "criteria": ["low", "high"]},
    "q3": {"type": "noul", "instructions": "judge it", "criteria": {"true": "yes", "false": "no"}},
}


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Stands in for an OpenerDirector; records the request and replays a scripted outcome."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def open(self, req, timeout=0):
        self.requests.append(req)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.invalid/jev", code, "status text", None, io.BytesIO(SECRET_BODY))


class StatusErrorTests(unittest.TestCase):
    def test_status_error_carries_code_only(self):
        err = HardenedJevStatusError(401)
        self.assertEqual(err.status, 401)
        self.assertIn("401", str(err))
        self.assertNotIn("secret", str(err))

    def test_status_error_is_a_jev_status_error_for_retry_compat(self):
        self.assertIsInstance(HardenedJevStatusError(429), JevStatusError)


class TransportTests(unittest.TestCase):
    def test_http_error_echoes_no_body(self):
        opener = FakeOpener(http_error(429))
        with mock.patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(HardenedJevStatusError) as ctx:
                hardened_jev_transport("https://example.invalid/jev", {"state": "s"}, {}, 5)
        self.assertEqual(ctx.exception.status, 429)
        self.assertNotIn("secret upstream detail", str(ctx.exception))
        self.assertNotIn("abc123", str(ctx.exception))

    def test_success_path_returns_parsed_json(self):
        opener = FakeOpener(FakeResponse(json.dumps({"answers": {"q1": {"answer": "a"}}}).encode()))
        with mock.patch("urllib.request.build_opener", return_value=opener):
            out = hardened_jev_transport("https://example.invalid/jev", {"state": "s"}, {"Authorization": "Bearer test-fixture"}, 5)
        self.assertEqual(out["answers"]["q1"]["answer"], "a")

    def test_opener_disables_proxy_environment(self):
        with mock.patch("urllib.request.build_opener") as bo:
            _jev_opener()
        handlers = bo.call_args.args
        proxies = [h for h in handlers if isinstance(h, urllib.request.ProxyHandler)]
        self.assertTrue(proxies, "opener must install an explicit ProxyHandler")
        self.assertEqual(proxies[0].proxies, {}, "ProxyHandler must be the no-proxy form ProxyHandler({})")

    def test_redirects_are_refused(self):
        handler = _NoTransportRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://evil.invalid/"))

    def test_non_finite_body_fails_before_any_network(self):
        for bad in (float("nan"), float("inf"), float("-inf"), 1e999):
            body = {"state": {"x": bad}, "questions": {}}
            with mock.patch("urllib.request.build_opener", side_effect=AssertionError("network must not be touched")):
                with self.subTest(bad=bad):
                    with self.assertRaises(ProviderError):
                        hardened_jev_transport("https://example.invalid/jev", body, {}, 5)

    def test_unreachable_raises_unavailable_without_url_or_detail(self):
        opener = FakeOpener(urllib.error.URLError("boom at https://example.invalid/jev"))
        with mock.patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderUnavailable) as ctx:
                hardened_jev_transport("https://example.invalid/jev", {"state": "s"}, {}, 5)
        self.assertNotIn("example.invalid", str(ctx.exception))
        self.assertNotIn("boom", str(ctx.exception))

    def test_invalid_json_response_is_a_provider_error(self):
        opener = FakeOpener(FakeResponse(b"not json"))
        with mock.patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                hardened_jev_transport("https://example.invalid/jev", {"state": "s"}, {}, 5)


class StateValidationTests(unittest.TestCase):
    def test_valid_states_pass_through(self):
        for state in ("plain text", "", {"a": [1, 2.5, True, None, "x"]}, ["a", "b"], 3, None):
            with self.subTest(state=state):
                self.assertIs(validate_state(state), state)

    def test_non_finite_numbers_rejected(self):
        for state in (float("nan"), {"x": float("inf")}, [{"y": -1e999}]):
            with self.subTest(state=state):
                with self.assertRaises(ProviderError):
                    validate_state(state)

    def test_non_serializable_states_rejected(self):
        for state in (b"bytes", {"k": object()}, {1: "int key"}, {("t",): "tuple key"}, object()):
            with self.subTest(state=state):
                with self.assertRaises(ProviderError):
                    validate_state(state)


class QuestionValidationTests(unittest.TestCase):
    def test_valid_questions_pass_through(self):
        self.assertIs(validate_jev_questions_strict(VALID_QUESTIONS), VALID_QUESTIONS)

    def test_non_text_ids_rejected(self):
        for qid in (1, b"q", None, "", "   "):
            with self.subTest(qid=qid):
                with self.assertRaises(ProviderError):
                    validate_jev_questions_strict({qid: {"type": "noul", "instructions": "judge"}})

    def test_non_text_instructions_rejected(self):
        for instructions in (["list"], {"k": "v"}, 42, None, "", "   "):
            with self.subTest(instructions=instructions):
                with self.assertRaises(ProviderError):
                    validate_jev_questions_strict({"q": {"type": "noul", "instructions": instructions}})

    def test_non_text_criteria_rejected(self):
        with self.assertRaises(ProviderError):
            validate_jev_questions_strict({"q": {"type": "choice", "instructions": "i", "criteria": {1: "x"}}})
        with self.assertRaises(ProviderError):
            validate_jev_questions_strict({"q": {"type": "choice", "instructions": "i", "criteria": {"a": 5}}})
        with self.assertRaises(ProviderError):
            validate_jev_questions_strict({"q": {"type": "score", "instructions": "i", "criteria": ["ok", 7]}})
        with self.assertRaises(ProviderError):
            validate_jev_questions_strict({"q": {"type": "noul", "instructions": "i", "criteria": {"true": 1}}})

    def test_documented_shape_checks_still_apply(self):
        with self.assertRaises(ProviderError):
            validate_jev_questions_strict({"q": {"type": "score", "instructions": "i", "criteria": ["only-one"]}})
        with self.assertRaises(ProviderError):
            validate_jev_questions_strict({"q": {"type": "bogus", "instructions": "i"}})


class UsageValidationTests(unittest.TestCase):
    def test_absent_usage_becomes_empty_map(self):
        self.assertEqual(validate_usage(None), {})

    def test_valid_usage_passes(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 0, "cost": 0.0025, "model": "jev-latest", "cached": True, "note": None}
        self.assertIs(validate_usage(usage), usage)

    def test_nested_finite_usage_is_accepted(self):
        u = {"tokens": {"in": 3, "out": 4}, "steps": [1, 2], "note": "ok"}
        self.assertEqual(validate_usage(u), u)

    def test_deep_or_cyclic_usage_and_state_are_provider_errors(self):
        deep = cyc = []
        for _ in range(5000):
            deep = [deep]
        cyc.append(cyc)
        for bad in (deep, cyc):
            with self.assertRaises(ProviderError):
                validate_state(bad)
            with self.assertRaises(ProviderError):
                validate_usage({"u": bad})

    def test_response_with_nan_or_infinity_is_rejected(self):
        for raw in (b'{"answers": {"q": NaN}}', b'{"answers": {"q": Infinity}}', b'{"answers": {"q": 1e999}}'):
            opener = FakeOpener(FakeResponse(raw))
            with mock.patch("urllib.request.build_opener", return_value=opener):
                with self.assertRaises(ProviderError):
                    hardened_jev_transport("https://example.invalid/jev", {"state": "s"}, {}, 5)

    def test_invalid_usage_rejected(self):
        for usage in ("text", [1], {"t": float("nan")}, {"t": float("inf")}, {"t": [float("nan")]}, {"t": {"n": float("inf")}}, {1: 2}):
            with self.subTest(usage=usage):
                with self.assertRaises(ProviderError):
                    validate_usage(usage)


class ParseResponseTests(unittest.TestCase):
    def test_valid_response(self):
        data = {"model": "m", "answers": {"q": {"answer": "a"}}, "usage": {"total": 1}}
        out = parse_jev_response(data, "fallback")
        self.assertEqual(out["model"], "m")
        self.assertEqual(out["usage"], {"total": 1})
        self.assertIs(out["raw"], data)

    def test_missing_answers_rejected(self):
        for data in (None, [], {}, {"answers": []}, {"answers": None}):
            with self.subTest(data=data):
                with self.assertRaises(ProviderError):
                    parse_jev_response(data, "m")

    def test_bad_usage_rejected(self):
        with self.assertRaises(ProviderError):
            parse_jev_response({"answers": {}, "usage": {"t": float("nan")}}, "m")


class GuardedEvaluateTests(unittest.TestCase):
    def make_jev(self, transport):
        # Explicit inert fixture strings so no environment keys are read.
        return JevEval(api_key="test-fixture-not-a-real-key", gateway_api_key="", transport=transport, sleeper=lambda s: None)

    def test_valid_round_trip(self):
        calls = []

        def transport(url, body, headers, timeout):
            calls.append((url, body, headers))
            return {"model": "jev-latest", "answers": {"q1": {"answer": "a"}}, "usage": {"total_tokens": 3}}

        jev = self.make_jev(transport)
        out = guarded_evaluate(jev, "some state", VALID_QUESTIONS)
        self.assertEqual(out["usage"], {"total_tokens": 3})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], {"Authorization": "Bearer test-fixture-not-a-real-key"})

    def test_invalid_inputs_fail_before_transport(self):
        def transport(*a):
            raise AssertionError("transport must not be called")

        jev = self.make_jev(transport)
        with self.assertRaises(ProviderError):
            guarded_evaluate(jev, {"x": float("nan")}, VALID_QUESTIONS)
        with self.assertRaises(ProviderError):
            guarded_evaluate(jev, "s", {"q": {"type": "noul", "instructions": 5}})

    def test_bad_usage_in_result_rejected(self):
        jev = self.make_jev(lambda *a: {"model": "m", "answers": {}, "usage": {"t": float("nan")}})
        with self.assertRaises(ProviderError):
            guarded_evaluate(jev, "s", VALID_QUESTIONS)

    def test_hardened_status_error_drives_existing_retry(self):
        attempts = []

        def transport(url, body, headers, timeout):
            attempts.append(1)
            if len(attempts) == 1:
                raise HardenedJevStatusError(429)
            return {"model": "m", "answers": {"q1": {"answer": "a"}}, "usage": {}}

        jev = self.make_jev(transport)
        out = guarded_evaluate(jev, "s", VALID_QUESTIONS)
        self.assertEqual(len(attempts), 2, "JevEval's 429 retry must still fire for the hardened error type")
        self.assertEqual(out["answers"]["q1"]["answer"], "a")

    def test_hosted_route_off_without_key(self):
        jev = JevEval(api_key="", gateway_api_key="", transport=lambda *a: (_ for _ in ()).throw(AssertionError("no call")))
        self.assertFalse(jev.available())
        with self.assertRaises(ProviderUnavailable):
            guarded_evaluate(jev, "s", VALID_QUESTIONS)


if __name__ == "__main__":
    unittest.main()


class DefaultPathTests(unittest.TestCase):
    """The default JevEval.evaluate path is hardened, not only the opt-in helpers."""

    def make(self, transport):
        return JevEval(api_key="test-fixture", transport=transport, sleeper=lambda s: None)

    def test_default_evaluate_rejects_bad_inputs_before_transport(self):
        calls = []
        jev = self.make(lambda *a: calls.append(a) or {"answers": {}})
        for state, qs in ((float("nan"), VALID_QUESTIONS), ("s", {1: VALID_QUESTIONS["q1"]}),
                          ("s", {"q": {"type": "noul", "instructions": 5}})):
            with self.assertRaises(ProviderError):
                jev.evaluate(state, qs)
        self.assertEqual(calls, [])

    def test_default_evaluate_rejects_bad_usage_but_keeps_absent_usage(self):
        with self.assertRaises(ProviderError):
            self.make(lambda *a: {"answers": {}, "usage": [1]}).evaluate("s", VALID_QUESTIONS)
        self.assertEqual(self.make(lambda *a: {"answers": {}}).evaluate("s", VALID_QUESTIONS)["usage"], {})

    def test_status_error_never_echoes_detail(self):
        self.assertNotIn("secret", str(JevStatusError(500, "secret body")))
