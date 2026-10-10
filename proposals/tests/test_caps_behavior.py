"""AUTHORED, NOT RUN. Needs proposals/sm-caps.patch applied. Fake response objects only: no sockets, no network."""
import unittest
from instinct_models import providers, health


class Fake:
    def __init__(self, chunks): self.chunks = list(chunks); self.sizes = []
    def read1(self, n=-1):
        self.sizes.append(n)
        return self.chunks.pop(0) if self.chunks else b""


class Clock:
    def __init__(self, step): self.t, self.step = 0.0, step
    def __call__(self): self.t += self.step; return self.t


class CapsBehavior(unittest.TestCase):
    def test_under_cap_returns_whole_body(self):
        self.assertEqual(providers._read_capped(Fake([b'{"a"', b':1}']), 100, 5), b'{"a":1}')

    def test_exactly_cap_ok_one_over_fails_generic(self):
        self.assertEqual(providers._read_capped(Fake([b"x" * 10]), 10, 5), b"x" * 10)
        with self.assertRaises(providers.ProviderError) as c:
            providers._read_capped(Fake([b"SECRETBODY" * 3]), 10, 5)
        self.assertEqual(str(c.exception), "provider response too large")
        self.assertNotIn("SECRET", str(c.exception))

    def test_read_requests_never_exceed_remaining_plus_one(self):
        f = Fake([b"x" * 3, b"y" * 3]); providers._read_capped(f, 10, 5)
        self.assertTrue(all(n <= 11 for n in f.sizes))

    def test_deadline_is_generic_and_status_less(self):
        with self.assertRaises(providers.ProviderError) as c:
            providers._read_capped(Fake([b"a"] * 50), 1000, 3, clock=Clock(1.0))
        self.assertEqual(str(c.exception), "provider response too slow")
        self.assertIsNone(getattr(c.exception, "status", None))

    def test_delayed_terminal_eof_is_too_slow_not_success(self):
        # no data at all: the first read IS the terminal EOF, and the clock is past the deadline only after it returns
        times = iter([0.0, 0.5, 9.0])  # start, before read, after the terminal read
        with self.assertRaises(providers.ProviderError) as c:
            providers._read_capped(Fake([]), 100, 3, clock=lambda: next(times))
        self.assertEqual(str(c.exception), "provider response too slow")

    def test_late_eof_after_a_good_read_is_too_slow(self):
        times = iter([0.0, 0.1, 0.2, 0.3, 9.0])  # start, pre/post read 1 (ok), pre read 2, post terminal read 2 (late)
        with self.assertRaises(providers.ProviderError) as c:
            providers._read_capped(Fake([b"ok"]), 100, 3, clock=lambda: next(times))
        self.assertEqual(str(c.exception), "provider response too slow")

    def test_expired_before_next_read_does_not_start_it(self):
        f = Fake([b"a", b"b"])
        times = iter([0.0, 0.1, 0.2, 99.0])  # start, pre-read1, post-read1, pre-read2 (expired)
        with self.assertRaises(providers.ProviderError):
            providers._read_capped(f, 100, 3, clock=lambda: next(times))
        self.assertEqual(len(f.sizes), 1)

    def test_health_delayed_eof_and_validation(self):
        times = iter([0.0, 0.1, 99.0])
        with self.assertRaises(ValueError) as c:
            health._read_capped(Fake([]), 8, 3, clock=lambda: next(times))
        self.assertEqual(str(c.exception), "response too slow")
        for v in (0, -1, True, "8", 1.5, None):
            with self.assertRaises(ValueError, msg=v):
                health._get("http://127.0.0.1:1/models", None, 1, v)
        r = health.probe("http://127.0.0.1:1", "m", None, 1, True)
        self.assertFalse(r["ok"]); self.assertEqual(r["error"], "max_bytes must be a positive integer")

    def test_openclaw_default_transport_really_forwards_the_cap_to_http_json(self):
        from unittest import mock
        url = "http://127.0.0.1:1/v1/chat/completions"
        o = providers.OpenClawOwner("http://127.0.0.1:1", "tok", max_response_bytes=123)
        self.assertIs(o.transport.func, providers._openclaw_http)
        with mock.patch.object(providers, "http_json", return_value={"ok": 1}) as hj:
            self.assertEqual(o.transport(url, {"b": 1}, {"h": 2}, 5), {"ok": 1})
        hj.assert_called_once_with(url, {"b": 1}, {"h": 2}, 5, 123)
        d = providers.OpenClawOwner("http://127.0.0.1:1", "tok")
        self.assertIs(d.transport, providers._openclaw_http)
        with mock.patch.object(providers, "http_json", return_value={}) as hj2:
            d.transport(url, {}, {}, 5)
        hj2.assert_called_once_with(url, {}, {}, 5, providers.DEFAULT_MAX_RESPONSE_BYTES)

    def test_direct_entry_points_reject_bad_max_bytes_before_any_network_use(self):
        from unittest import mock
        with mock.patch("urllib.request.build_opener") as bo, mock.patch.object(providers, "_jev_opener") as jo, \
                mock.patch("urllib.request.urlopen") as uo:
            for fn in (providers.http_json, providers._jev_http, providers._openclaw_http):
                for bad in (True, 0, -1, "8", None, 1.5):
                    with self.assertRaises(ValueError, msg=(fn.__name__, bad)):
                        fn("http://127.0.0.1:1/x", {"a": 1}, {}, 5, bad)
        bo.assert_not_called(); jo.assert_not_called(); uo.assert_not_called()

    def test_bad_cap_values_rejected(self):
        for v in (0, -1, True, "8", 1.5, None):
            with self.assertRaises(ValueError, msg=v):
                providers._check_max_bytes(v)

    def test_constructor_cap_wires_default_transport_only(self):
        p = providers.InklingHFRouter("m", token="t", max_response_bytes=123)
        self.assertEqual(p.transport.keywords, {"max_bytes": 123})
        calls = []
        custom = lambda u, b, h, t: calls.append(1) or {}
        q = providers.InklingHFRouter("m", token="t", transport=custom, max_response_bytes=123)
        self.assertIs(q.transport, custom)

    def test_health_generic_errors_and_separate_defaults(self):
        with self.assertRaises(ValueError) as c:
            health._read_capped(Fake([b"z" * 9]), 8, 5)
        self.assertEqual(str(c.exception), "response too large")
        self.assertEqual(health.DEFAULT_MODEL_LIST_MAX_BYTES, 64 * 1024 * 1024)
        self.assertEqual(providers.DEFAULT_MAX_RESPONSE_BYTES, 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
