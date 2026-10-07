import unittest
from instinct_models.providers import LOCAL, ChatResult, Provider
from instinct_models.router import Router, Task


class Boom(Provider):
    name, locality = "boom", LOCAL

    def available(self):
        return True

    def chat(self, messages, *, tools=None, max_tokens=1024):
        raise KeyError("unexpected")


class Fine(Provider):
    name, locality = "fine", LOCAL

    def available(self):
        return True

    def chat(self, messages, *, tools=None, max_tokens=1024):
        return ChatResult("fine", "m", "hi", [], {})


class RouterIsolationTests(unittest.TestCase):
    def test_unexpected_provider_exception_escalates_not_crashes(self):
        r = Router([Boom(), Fine()]).run(Task([{"role": "user", "content": "x"}]))
        self.assertTrue(r.ok)
        self.assertEqual(r.attempts[0].outcome, "error")
        self.assertEqual(r.attempts[1].outcome, "ok")
