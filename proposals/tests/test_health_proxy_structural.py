"""AUTHORED, NOT RUN. Needs proposals/sm-caps.patch THEN proposals/sm-proxy-stacked-on-caps.patch applied.
Structural and environment-independent. getproxies is mocked to a SYNTHETIC non-empty dict, so an ambient-environment
ProxyHandler() mutant (or a missing explicit handler, which lets build_opener add its default ProxyHandler) would read it.
The real build_opener is WRAPPED (spied), not replaced; OpenerDirector.open is mocked: no network, proxy or credentials.
Note: the real build_opener does not keep an empty ProxyHandler in opener.handlers (it has no *_open methods), so the
explicit handler is asserted on the build_opener ARGUMENTS and the resulting opener is asserted to carry no proxy methods."""
import unittest
import urllib.request
from unittest import mock

from instinct_models import health

SYNTHETIC = {"http": "http://synthetic-proxy.invalid:3128", "https": "http://synthetic-proxy.invalid:3128"}
real_build_opener = urllib.request.build_opener


class HealthProxy(unittest.TestCase):
    def run_get(self):
        captured = {}

        def spy(*handlers):
            opener = real_build_opener(*handlers)
            captured["args"], captured["opener"] = handlers, opener
            return opener

        with mock.patch("urllib.request.getproxies", return_value=dict(SYNTHETIC)) as gp, \
                mock.patch("urllib.request.build_opener", side_effect=spy), \
                mock.patch.object(urllib.request.OpenerDirector, "open", autospec=True, side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                health._get("http://127.0.0.1:1/models", "key", 1)
        return captured, gp

    def test_build_opener_gets_explicit_empty_proxy_handler_and_no_redirect(self):
        captured, gp = self.run_get()
        proxies = [h for h in captured["args"] if isinstance(h, urllib.request.ProxyHandler)]
        self.assertEqual(len(proxies), 1, "build_opener must be given one explicit ProxyHandler")
        self.assertEqual(proxies[0].proxies, {})
        self.assertTrue(any(isinstance(h, health._NoRedirect) for h in captured["args"]))
        gp.assert_not_called()  # an ambient ProxyHandler() (explicit or build_opener's default) would call it

    def test_resulting_opener_has_no_environment_proxy_methods(self):
        captured, _ = self.run_get()
        opener = captured["opener"]
        for h in opener.handlers:
            if isinstance(h, urllib.request.ProxyHandler):
                self.assertEqual(h.proxies, {})
        for scheme in ("http", "https"):
            self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) and hasattr(h, scheme + "_open") for h in opener.handlers),
                             "no handler may route %s through the synthetic proxy" % scheme)
        self.assertTrue(any(isinstance(h, health._NoRedirect) for h in opener.handlers))


if __name__ == "__main__":
    unittest.main()
