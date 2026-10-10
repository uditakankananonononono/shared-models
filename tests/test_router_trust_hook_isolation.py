"""Synthetic failing-first assertions, authored NOT RUN; proposal is unapplied."""
import unittest
from instinct_models.router import Router, Task, ChatResult, Provider, ProviderError


class PolicyProvider(Provider):
    def __init__(self, name, policy=True, failure=None):
        self.name, self.policy, self.failure = name, policy, failure
        self.calls = []

    def allows_private(self):
        self.calls.append("policy")
        if self.failure is not None:
            raise self.failure
        return self.policy

    def available(self):
        self.calls.append("available")
        return True

    def chat(self, messages, *, tools=None, max_tokens=1024):
        self.calls.append("chat")
        return ChatResult(self.name, "synthetic", "ok", [], {})


class TrustHookIsolationTests(unittest.TestCase):
    def test_raising_policy_is_generic_error_then_next_trusted_provider(self):
        # Expected to error on the pinned source before its exception boundary.
        for error in (RuntimeError("synthetic-private-detail"), ProviderError("synthetic-private-detail")):
            with self.subTest(error=type(error).__name__):
                broken = PolicyProvider("broken", failure=error)
                trusted = PolicyProvider("trusted")
                out = Router([broken, trusted]).run(Task([], private=True))
                self.assertTrue(out.ok)
                self.assertEqual([a.outcome for a in out.attempts], ["error", "ok"])
                self.assertEqual(out.attempts[0].detail, "provider failed")
                self.assertNotIn("synthetic-private-detail", repr(out.attempts))
                self.assertEqual(broken.calls, ["policy"])
                self.assertEqual(trusted.calls, ["policy", "available", "chat"])

    def test_raising_policy_alone_never_grants_or_records_denial(self):
        broken = PolicyProvider("broken", failure=RuntimeError("synthetic-private-detail"))
        out = Router([broken]).run(Task([], private=True))
        self.assertFalse(out.ok)
        self.assertEqual([(a.outcome, a.detail) for a in out.attempts], [("error", "provider failed")])
        self.assertEqual(broken.calls, ["policy"])

    def test_false_policy_still_skips_before_availability_and_chat(self):
        denied = PolicyProvider("denied", policy=False)
        out = Router([denied, PolicyProvider("trusted")]).run(Task([], private=True))
        self.assertTrue(out.ok)
        self.assertEqual([a.outcome for a in out.attempts], ["skipped", "ok"])
        self.assertEqual(denied.calls, ["policy"])

    def test_public_task_never_invokes_private_policy(self):
        public = PolicyProvider("public", failure=RuntimeError("must not call"))
        out = Router([public]).run(Task([], private=False))
        self.assertTrue(out.ok)
        self.assertEqual(public.calls, ["available", "chat"])
