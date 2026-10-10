import unittest
from types import SimpleNamespace

from instinct_models.providers import fix_needle_engine


class EngineOverrideFormat(unittest.TestCase):
    def mod(self):
        return SimpleNamespace(ENGINE_VERSIONS={3: "3.0.2"})

    def test_malformed_override_is_rejected_and_pin_untouched(self):
        for bad in ("../../etc/x", "3.0", "3.0.2.1", "v3.0.2", "3.0.2 ", "3.0.2/../x", "a.b.c", "3.0.2\n", "1234.0.0",
                    "\u0663.\u0660.\u0662", "\uff13.\uff10.\uff12", "3.0.\u0662"):
            m = self.mod()
            with self.assertRaises(ValueError, msg=bad):
                fix_needle_engine(m, env={"INSTINCT_NEEDLE_ENGINE_V3": bad})
            self.assertEqual(m.ENGINE_VERSIONS[3], "3.0.2", bad)

    def test_well_formed_override_still_applies(self):
        m = self.mod()
        self.assertEqual(fix_needle_engine(m, env={"INSTINCT_NEEDLE_ENGINE_V3": "3.2.0"}), "3.2.0")

    def test_malformed_env_makes_needle_unavailable_not_a_crash(self):
        import sys, types, os
        from unittest import mock
        from instinct_models.providers import NeedleLocal
        fetch = types.SimpleNamespace(ENGINE_VERSIONS={3: "3.0.2"})
        needle = types.ModuleType("needle"); agent = types.ModuleType("needle.agent")
        agent.fetch = fetch; needle.agent = agent; needle.Needle = object
        with mock.patch.dict(sys.modules, {"needle": needle, "needle.agent": agent}), \
             mock.patch.dict(os.environ, {"INSTINCT_NEEDLE_ENGINE_V3": "\u0663.\u0660.\u0662"}):
            self.assertFalse(NeedleLocal().available())
        self.assertEqual(fetch.ENGINE_VERSIONS[3], "3.0.2")


if __name__ == "__main__":
    unittest.main()
