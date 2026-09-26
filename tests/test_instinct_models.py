import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from subprocess import CompletedProcess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from instinct_models import Router, Task, load_config
from instinct_models.catalog import AILibraryCatalog
from instinct_models.providers import (InklingHFRouter, JevEval, JevStatusError, NeedleLocal, OrnithOpenAICompat,
                                       ProviderError, ProviderUnavailable)
from instinct_models.training import (ExampleRow, NeedleLoRAJob, OrnithRLUnavailable, build_needle_jsonl,
                                      ornith_rl_preflight, train_needle_lora)

TOOLS = [{"name": "log_obligation", "parameters": {"type": "object", "properties": {"party": {"type": "string"}, "due": {"type": "string"}}}}]


def oa_reply(content="", calls=None):
    msg = {"content": content}
    if calls:
        msg["tool_calls"] = [{"function": {"name": n, "arguments": json.dumps(a)}} for n, a in calls]
    return {"choices": [{"message": msg}]}


class FakeNeedle:
    def __init__(self, reply): self.reply = reply
    def __call__(self, **kw): self.kw = kw; return self
    def complete(self, q, max_new_tokens=256): self.q = q; return self.reply


class RouterTests(unittest.TestCase):
    def test_needle_first_then_escalates_on_low_confidence(self):
        seen = []
        orn = OrnithOpenAICompat("http://o/v1", "ornith", transport=lambda u, b, h, t: seen.append(u) or oa_reply(calls=[("log_obligation", {"party": "Acme"})]))
        low = NeedleLocal(factory=FakeNeedle({"type": "call", "success": True, "function_calls": [{"name": "log_obligation", "arguments": {}}], "confidence": 0.3}))
        out = Router([low, orn]).run(Task([{"role": "user", "content": "Acme owes a report"}], tools=TOOLS))
        self.assertEqual(out.result.provider, "ornith-local")
        self.assertEqual([a.outcome for a in out.attempts], ["escalated", "ok"])
        hi = NeedleLocal(factory=FakeNeedle({"type": "call", "success": True, "function_calls": [{"name": "log_obligation", "arguments": {"party": "Acme"}}], "confidence": 0.95}))
        self.assertEqual(Router([hi, orn]).run(Task([{"role": "user", "content": "Acme"}], tools=TOOLS)).result.provider, "needle-local")

    def test_private_never_hosted_and_generation_skips_needle(self):
        hosted = InklingHFRouter("thinkingmachines/Inkling-Small", token="t", transport=lambda *a: oa_reply("hi"))
        r = Router([NeedleLocal(factory=FakeNeedle({})), hosted])
        out = r.run(Task([{"role": "user", "content": "contract text"}], private=True))
        self.assertFalse(out.ok)
        self.assertEqual([a.outcome for a in out.attempts], ["skipped", "skipped"])
        self.assertEqual(r.run(Task([{"role": "user", "content": "hi"}])).result.text, "hi")

    def test_config_from_env(self):
        cfg = load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_ORNITH_URL": "http://localhost:11434/v1", "INSTINCT_ALLOW_HOSTED": "0"})
        names = [p.name for p in Router.from_config(cfg).providers]
        self.assertEqual(names, ["needle-local", "ornith-local", "inkling-local"])
        with self.assertRaises(ValueError):
            load_config({"INSTINCT_PRODUCT": "other"})

    def test_unconfigured_providers(self):
        self.assertFalse(OrnithOpenAICompat(None, None).available())
        with self.assertRaises(ProviderUnavailable):
            NeedleLocal(factory=FakeNeedle({})).chat([{"role": "user", "content": "x"}])


class DS:
    product = "atlas"
    def __init__(self, rows): self._rows = rows
    def rows(self): return self._rows


class TrainingTests(unittest.TestCase):
    def rows(self):
        return [ExampleRow("Acme must deliver the audit by 2026-10-01", TOOLS, [{"name": "log_obligation", "arguments": {"party": "Acme", "due": "2026-10-01"}}], True, "m07:1"),
                ExampleRow("what's the weather", TOOLS, [], True, "neg:1"),
                ExampleRow("Beta pays", TOOLS, [{"name": "log_obligation", "arguments": {"party": "Gamma"}}], True, "m07:2"),
                ExampleRow("Delta owes", TOOLS, [{"name": "log_obligation", "arguments": {"party": "Delta"}}], False, "m07:3")]

    def test_dataset_filters_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            m = build_needle_jsonl(DS(self.rows()), Path(d) / "atlas.jsonl")
            self.assertEqual((m["rows"], m["dropped"]), (2, 2))
            reasons = {x["source_ref"]: x["reason"] for x in m["dropped_detail"]}
            self.assertIn("not present", reasons["m07:2"]); self.assertIn("not owner-confirmed", reasons["m07:3"])
            self.assertTrue(m["train_locally_only"])
            lines = (Path(d) / "atlas.jsonl").read_text().splitlines()
            self.assertEqual(json.loads(lines[1])["answers"], [])

    def test_lora_runs_documented_cli_without_upload(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            build_needle_jsonl(DS(self.rows()), Path(d) / "atlas.jsonl")
            def runner(cmd, env):
                calls.append((cmd, env))
                if cmd[1] == "build":
                    Path(cmd[cmd.index("--out") + 1]).write_bytes(b"cact")
                return CompletedProcess(cmd, 0, "ok", "")
            os.environ["NEEDLE_HF_REPO"] = "someone/repo"
            try:
                rec = train_needle_lora(NeedleLoRAJob("atlas", str(Path(d) / "atlas.jsonl"), str(Path(d) / "out")), runner=runner)
            finally:
                del os.environ["NEEDLE_HF_REPO"]
            self.assertEqual([c[0][1] for c in calls], ["finetune", "build"])
            self.assertTrue(all("--upload" not in c[0] and "NEEDLE_HF_REPO" not in c[1] for c in calls))
            self.assertEqual(len(rec["tuned_sha256"]), 64)
            self.assertTrue((Path(d) / "out" / "registry.jsonl").exists())
            (Path(d) / "atlas.jsonl").write_text("tampered\n")
            with self.assertRaises(ValueError):
                train_needle_lora(NeedleLoRAJob("atlas", str(Path(d) / "atlas.jsonl"), str(Path(d) / "out")), runner=runner)

    def test_ornith_rl_refuses_without_gpu(self):
        with self.assertRaises(OrnithRLUnavailable):
            ornith_rl_preflight(probe=lambda: 24.0)
        self.assertTrue(ornith_rl_preflight(probe=lambda: 160.0)["ok"])


class CatalogTests(unittest.TestCase):
    def test_reads_listings_respects_robots(self):
        pages = {"https://www.theailibrary.co/robots.txt": "User-agent: *\nDisallow: /admin\n",
                 "https://www.theailibrary.co/prompts": '<a href="/prompts/cold-email">Cold email prompt</a><a href="/pricing">Pricing</a>'
                                                         '<a href="https://other.test/x">Offsite</a><a href="/tools/notion-ai/">Notion AI</a>'}
        c = AILibraryCatalog(fetch=lambda u: pages[u], min_interval_s=0)
        items = c.browse("prompts")
        self.assertEqual([(i.title, i.kind) for i in items], [("Cold email prompt", "prompt"), ("Notion AI", "tool")])
        self.assertEqual(len(c.browse("prompts", query="notion")), 1)
        blocked = AILibraryCatalog(fetch=lambda u: "User-agent: *\nDisallow: /\n" if u.endswith("robots.txt") else "", min_interval_s=0)
        with self.assertRaises(PermissionError):
            blocked.browse("prompts")
        self.assertFalse(hasattr(c, "submit"))


class HardeningTests(unittest.TestCase):
    def test_needle_ungrounded_call_escalates(self):
        orn = OrnithOpenAICompat("http://o/v1", "ornith", transport=lambda u, b, h, t: oa_reply(calls=[("log_obligation", {"party": "Acme"})]))
        bad = NeedleLocal(factory=FakeNeedle({"type": "call", "success": True, "confidence": 0.99,
                                              "function_calls": [{"name": "log_obligation", "arguments": {"party": "Zeta"}}],
                                              "validation": {"ungrounded": ["log_obligation.party"]}}))
        out = Router([bad, orn]).run(Task([{"role": "user", "content": "Acme owes a report"}], tools=TOOLS))
        self.assertEqual(out.result.provider, "ornith-local")
        self.assertEqual(out.attempts[0].outcome, "escalated")

    def test_needle_telemetry_off_by_default(self):
        import types
        old_env, old_mod = os.environ.pop("NEEDLE_TELEMETRY", None), sys.modules.get("needle")
        fake = types.ModuleType("needle"); fake.Needle = FakeNeedle({})
        sys.modules["needle"] = fake
        try:
            NeedleLocal()._factory()
            self.assertEqual(os.environ.get("NEEDLE_TELEMETRY"), "0")
            self.assertEqual(os.environ.get("DO_NOT_TRACK"), "1")
            os.environ.pop("NEEDLE_TELEMETRY"); os.environ.pop("DO_NOT_TRACK", None)
            NeedleLocal(telemetry=True)._factory()
            self.assertIsNone(os.environ.get("NEEDLE_TELEMETRY"))
        finally:
            if old_mod is None:
                sys.modules.pop("needle", None)
            else:
                sys.modules["needle"] = old_mod
            if old_env is not None:
                os.environ["NEEDLE_TELEMETRY"] = old_env

    def test_cross_product_rows_are_dropped(self):
        rows = [ExampleRow("Acme owes a report", TOOLS, [{"name": "log_obligation", "arguments": {"party": "Acme"}}], True, "a:1", product="atlas"),
                ExampleRow("Remind me to call mom", TOOLS, [], True, "m:1", product="meemee"),
                ExampleRow("what's the weather", TOOLS, [], True, "neg:1")]
        with tempfile.TemporaryDirectory() as d:
            m = build_needle_jsonl(DS(rows), Path(d) / "atlas.jsonl")
            self.assertEqual((m["rows"], m["dropped"]), (2, 1))
            self.assertIn("belongs to 'meemee'", m["dropped_detail"][0]["reason"])


class NeedleEngineTests(unittest.TestCase):
    def test_unpublished_engine_pin_is_mapped_to_published(self):
        from types import SimpleNamespace
        from instinct_models.providers import fix_needle_engine
        f = SimpleNamespace(ENGINE_VERSIONS={2: "2.0.4", 3: "3.0.2"})
        self.assertEqual(fix_needle_engine(f, env={}), "3.0.1")
        f = SimpleNamespace(ENGINE_VERSIONS={2: "2.0.4", 3: "3.0.2"})
        self.assertEqual(fix_needle_engine(f, env={"INSTINCT_NEEDLE_ENGINE_V3": "3.0.0"}), "3.0.0")
        f = SimpleNamespace(ENGINE_VERSIONS={2: "2.0.4", 3: "3.0.9"})
        self.assertEqual(fix_needle_engine(f, env={}), "3.0.9")  # unknown pins are left alone
        self.assertIsNone(fix_needle_engine(SimpleNamespace(), env={}))

    def test_falls_back_to_needle2_only_for_base_model(self):
        from instinct_models.providers import needle_with_fallback
        calls = []

        def cls(**kw):
            calls.append(kw)
            if kw.get("generation") != 2:
                raise RuntimeError("404 Entry Not Found")
            return "agent-v2"
        self.assertEqual(needle_with_fallback(cls)(tools=TOOLS), "agent-v2")
        self.assertEqual(calls[-1], {"generation": 2, "tools": TOOLS})
        with self.assertRaises(RuntimeError):
            needle_with_fallback(cls)(tools=TOOLS, weights="tuned.cact")

        def broken(**kw):
            raise RuntimeError("no engine")
        with self.assertRaises(ProviderUnavailable):
            needle_with_fallback(broken)(tools=TOOLS)

    def test_real_factory_applies_engine_fix(self):
        import types
        old = {k: sys.modules.get(k) for k in ("needle", "needle.agent", "needle.agent.fetch")}
        fetch = types.ModuleType("needle.agent.fetch"); fetch.ENGINE_VERSIONS = {2: "2.0.4", 3: "3.0.2"}
        agent = types.ModuleType("needle.agent"); agent.fetch = fetch
        pkg = types.ModuleType("needle"); pkg.Needle = FakeNeedle({}); pkg.agent = agent
        sys.modules.update({"needle": pkg, "needle.agent": agent, "needle.agent.fetch": fetch})
        try:
            NeedleLocal(telemetry=True)._factory()
            self.assertEqual(fetch.ENGINE_VERSIONS[3], "3.0.1")
        finally:
            for k, v in old.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v




class JevTests(unittest.TestCase):
    Q = {"is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"}}

    def test_unavailable_without_key(self):
        j = JevEval(api_key="", gateway_api_key="", transport=lambda *a: {})
        self.assertFalse(j.available())
        with self.assertRaises(ProviderUnavailable):
            j.evaluate("state", self.Q)
        with self.assertRaises(ProviderUnavailable):
            j.chat([{"role": "user", "content": "hi"}])

    def test_evaluate_happy_path(self):
        seen = {}
        def fake(url, body, headers, timeout):
            seen.update(url=url, body=body, headers=headers)
            return {"model": "jev-1.13.0", "answers": {"is_urgent": {"type": "noul", "noul": 0.95}},
                    "usage": {"input_tokens": 10, "output_tokens": 2}}
        out = JevEval(api_key="sk-test", transport=fake).evaluate("Help! Payouts failing.", self.Q)
        self.assertEqual(seen["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(seen["body"]["model"], "jev-latest")
        self.assertEqual(seen["body"]["state"], "Help! Payouts failing.")
        self.assertEqual(out["answers"]["is_urgent"]["noul"], 0.95)
        self.assertEqual(out["usage"]["input_tokens"], 10)

    def test_gateway_preferred_and_direct_alternate(self):
        seen = {}
        def fake(url, body, headers, timeout):
            seen.update(url=url, body=body, headers=headers)
            return {"answers": {"is_urgent": {"type": "noul", "noul": 0.5}}}
        with mock.patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "gw-test"}):
            j = JevEval(api_key="direct-test", transport=fake)
            self.assertTrue(j.available())
            j.evaluate("state", self.Q)
        self.assertEqual(seen["url"], "https://ai-gateway.vercel.sh/typesafe/v1/systemone")
        self.assertEqual(seen["body"]["model"], "typesafe-ai/jev")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer gw-test")
        j = JevEval(api_key="direct-test", gateway_api_key="", transport=fake)
        j.evaluate("state", self.Q)
        self.assertEqual(seen["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(seen["body"]["model"], "jev-latest")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer direct-test")

    def test_validation(self):
        j = JevEval(api_key="k", transport=lambda *a: {"answers": {}})
        with self.assertRaises(ProviderError):
            j.evaluate("s", {})
        with self.assertRaises(ProviderError):
            j.evaluate("s", {"q": {"type": "essay", "instructions": "x"}})
        with self.assertRaises(ProviderError):
            j.evaluate("s", {"q": {"type": "choice", "instructions": "x"}})  # criteria required
        with self.assertRaises(ProviderError):
            j.evaluate("s", {"q": {"type": "score", "instructions": "x", "criteria": ["only one level"]}})
        with self.assertRaises(ProviderError):
            j.evaluate("s", {"q": {"type": "noul", "instructions": "x", "criteria": ["not", "a", "map"]}})
        ok = {"q": {"type": "choice", "instructions": "x", "criteria": {"a": "opt a", "b": "opt b"}}}
        j.evaluate("s", ok)  # valid choice passes

    def test_retry_on_429_then_success(self):
        calls, sleeps = [], []
        def flaky(url, body, headers, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise JevStatusError(429, "rate limited")
            return {"answers": {"is_urgent": {"noul": 0.5}}}
        out = JevEval(api_key="k", transport=flaky, sleeper=sleeps.append).evaluate("s", self.Q)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(out["answers"]["is_urgent"]["noul"], 0.5)

    def test_429_exhausted_and_401(self):
        def always429(*a): raise JevStatusError(429, "x")
        with self.assertRaises(JevStatusError):
            JevEval(api_key="k", transport=always429, sleeper=lambda s: None).evaluate("s", self.Q)
        def always401(*a): raise JevStatusError(401, "bad key")
        with self.assertRaisesRegex(ProviderError, "401"):
            JevEval(api_key="k", transport=always401).evaluate("s", self.Q)

    def test_config_reads_jev_key(self):
        self.assertEqual(load_config({"INSTINCT_PRODUCT": "atlas", "INSTINCT_JEV_API_KEY": "sk-1"}).jev_api_key, "sk-1")
        self.assertEqual(load_config({"INSTINCT_PRODUCT": "atlas", "JEV_API_KEY": "sk-2"}).jev_api_key, "sk-2")
        self.assertIsNone(load_config({"INSTINCT_PRODUCT": "atlas"}).jev_api_key)


if __name__ == "__main__":
    unittest.main()


def test_health_probe_unreachable_never_raises():
    from instinct_models.health import probe, hf_token_valid
    r = probe("http://127.0.0.1:9/v1", "m")
    assert r["ok"] is False and "error" in r
    assert hf_token_valid(None) is False
