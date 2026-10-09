import unittest

from instinct_models.providers import ChatResult, Provider
from instinct_models.router import Router, Task

T = [{"name": "x"}]
MSG = [{"role": "user", "content": "hi"}]


class Fake(Provider):
    def __init__(self, name, res):
        self.name, self.res = name, res

    def available(self):
        return True

    def allows_private(self):
        return True

    def chat(self, messages, tools=None, max_tokens=0):
        return self.res


GOOD = ChatResult("good", "m", "hello", [{"name": "x", "arguments": {}}], {})


class MalformedProviderResult(unittest.TestCase):
    def test_bad_shapes_are_errors_and_chain_continues(self):
        for bad in (None, "hi", {"a": 1}, ChatResult("b", "m", "t", None, {})):
            for tools in (None, T):
                out = Router([Fake("bad", bad), Fake("good", GOOD)]).run(Task(MSG, tools))
                self.assertTrue(out.ok, (bad, tools))
                self.assertEqual([a.outcome for a in out.attempts], ["error", "ok"])
                self.assertEqual(out.result.provider, "good")

    def test_private_detail_is_redacted(self):
        out = Router([Fake("bad", None)]).run(Task(MSG, T, private=True))
        self.assertFalse(out.ok)
        self.assertEqual(out.attempts[0].detail, "provider failed")


if __name__ == "__main__":
    unittest.main()
