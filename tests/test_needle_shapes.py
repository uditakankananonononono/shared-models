import unittest
from instinct_models import Router, Task
from instinct_models.providers import NeedleLocal, ProviderError
class NeedleShapesTests(unittest.TestCase):
    def test_malformed_tool_calls_become_provider_error(self):
        class Agent:
            def __init__(self,out):self.out=out
            def complete(self,*a,**kw):return self.out
        for calls in ([None],[{}],[{'name':'x','arguments':[]}],{'name':'x'}):
            with self.subTest(calls=calls):
                p=NeedleLocal(factory=lambda **kw:Agent({'type':'call','function_calls':calls}))
                with self.assertRaises(ProviderError):p.chat([{'role':'user','content':'fixture'}],tools=[{'name':'x'}])
                out=Router([p]).run(Task([],tools=[{'name':'x'}],private=True))
                self.assertFalse(out.ok)
                self.assertEqual(out.attempts[0].outcome,'error')
