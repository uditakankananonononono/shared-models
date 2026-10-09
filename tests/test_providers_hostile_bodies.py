import unittest

from instinct_models.providers import InklingLocal, NeedleLocal, ProviderError


def chat_with(body):
    p = InklingLocal("http://127.0.0.1:1", "m", transport=lambda u, b, h, t: body)
    return p.chat([{"role": "user", "content": "x"}])


def call(args):
    return {"choices": [{"message": {"tool_calls": [{"function": {"name": "t", "arguments": args}}]}}]}


class Agent:
    def __init__(self, out):
        self.out = out

    def complete(self, q, max_new_tokens=0):
        return self.out


def needle(out):
    n = NeedleLocal(weights=None, factory=lambda **kw: Agent(out))
    return n.chat([{"role": "user", "content": "x"}], tools=[{"name": "t"}])


class HostileBodies(unittest.TestCase):
    def test_deeply_nested_arguments_are_a_provider_error(self):
        for args in ("[" * 100000 + "]" * 100000, '{"a":' * 100000 + "1" + "}" * 100000):
            with self.assertRaises(ProviderError):
                chat_with(call(args))

    def test_non_finite_constants_in_arguments_are_a_provider_error(self):
        for args in ('{"a": NaN}', '{"a": Infinity}', '{"a": [-Infinity]}'):
            with self.assertRaises(ProviderError):
                chat_with(call(args))

    def test_normal_arguments_still_parse(self):
        self.assertEqual(chat_with(call('{"a": 1.5, "b": [1, 2]}')).tool_calls[0]["arguments"], {"a": 1.5, "b": [1, 2]})

    def test_needle_nan_confidence_escalates_and_good_confidence_passes(self):
        base = {"type": "call", "function_calls": [{"name": "t", "arguments": {}}]}
        self.assertEqual(needle({**base, "confidence": float("nan")}).tool_calls, [])
        self.assertEqual(needle({**base, "confidence": 0.5}).tool_calls, [])
        self.assertEqual(len(needle({**base, "confidence": 0.95}).tool_calls), 1)


if __name__ == "__main__":
    unittest.main()
