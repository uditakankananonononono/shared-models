"""Text-only; holds with the proposal unapplied."""
import pathlib
import unittest

R = pathlib.Path(__file__).resolve().parent.parent
S = (R / "proposals/sm-proxy-stacked-on-caps.patch").read_text()
T = (R / "proposals/tests/test_health_proxy_structural.py").read_text()


class HealthProxyText(unittest.TestCase):
    def test_patch_adds_explicit_empty_proxy_handler(self):
        self.assertIn("+    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())", S)
        self.assertIn("-    opener = urllib.request.build_opener(_NoRedirect())", S)

    def test_patch_touches_only_health(self):
        self.assertEqual(S.count("diff --git"), 1)
        self.assertIn("instinct_models/health.py", S)

    def test_structural_test_is_environment_independent(self):
        self.assertIn('mock.patch("urllib.request.getproxies"', T)
        self.assertIn("SYNTHETIC", T)
        self.assertIn("synthetic-proxy.invalid", T)

    def test_structural_test_spies_real_build_opener_and_asserts_getproxies_unused(self):
        self.assertIn("real_build_opener = urllib.request.build_opener", T)
        self.assertIn("gp.assert_not_called()", T)
        self.assertNotIn("len(proxies), 1)\n        self.assertEqual(proxies[0].proxies, {}, \"an ambient", T)


if __name__ == "__main__":
    unittest.main()
