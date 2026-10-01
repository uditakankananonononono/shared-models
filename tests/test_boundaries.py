"""Offline boundary tests. Fixture servers/transports are not model inference."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from instinct_models import Router, Task, load_config
from instinct_models.providers import InklingLocal, OrnithOpenAICompat, Provider, ProviderError, ChatResult
from instinct_models.catalog import AILibraryCatalog, _get

SECRET = 'private-synthetic-fixture'
def reply(text='ok', calls=None):
    msg = {'content': text}
    if calls is not None: msg['tool_calls'] = calls
    return {'choices': [{'message': msg}]}

class BoundaryTests(unittest.TestCase):
    def test_private_endpoint_guard_before_transport(self):
        urls = ['https://external.example/v1', 'http://192.168.1.2:8000/v1',
                'http://localhost.evil:8000/v1', 'http://127.0.0.1.evil:8000/v1',
                'http://2130706433:8000/v1', 'http://0177.0.0.1:8000/v1',
                'http://127.1:8000/v1', 'http://0x7f000001:8000/v1',
                'http://user:pass@localhost:8000/v1', 'http://@localhost:8000/v1',
                'http://localhost:8000/v1?x=1', 'http://localhost:8000/v1#x',
                'http://localhost/v1', 'http://localhost:bad/v1',
                'http://localhost:65536/v1', 'http://localhost:0/v1',
                'http://localhost:8000/v1?', 'http://localhost:8000/v1#',
                'http://localhost.:8000/v1', 'https://localhost:8000/v1',
                'http://localhost:8000/v1\n', 'http://localhost:8000\t/v1']
        for cls in (InklingLocal, OrnithOpenAICompat):
            for url in urls:
                with self.subTest(cls=cls.__name__, url=url):
                    seen=[]
                    p=cls(url, 'model', transport=lambda *a: seen.append(a) or reply())
                    self.assertFalse(Router([p]).run(Task([{'role':'user','content':SECRET}], private=True)).ok)
                    self.assertEqual(seen, [])

    def test_valid_loopback_and_remote_opt_in(self):
        for url in ('http://127.0.0.1:8000/v1','http://localhost:8000/v1','http://[::1]:8000/v1'):
            self.assertTrue(Router([InklingLocal(url,'m',transport=lambda *a: reply())]).run(Task([],private=True)).ok)
        p=InklingLocal('https://external.example/v1','m',trusted_remote=True,transport=lambda *a: reply())
        self.assertTrue(Router([p]).run(Task([],private=True)).ok)
        hosted=__import__('instinct_models.providers',fromlist=['InklingHFRouter']).InklingHFRouter('m',token='fixture',transport=lambda *a: reply())
        self.assertFalse(Router([hosted]).run(Task([],private=True)).ok)
        for url in ('https://user:pass@external.example/v1','https://external.example/v1?x=1'):
            self.assertFalse(Router([InklingLocal(url,'m',trusted_remote=True,transport=lambda *a: reply())]).run(Task([],private=True)).ok)
        cfg=load_config({'INSTINCT_PRODUCT':'atlas','INSTINCT_TRUST_REMOTE':'1','INSTINCT_ORNITH_URL':'https://external.example/v1','INSTINCT_ORNITH_MODEL':'m'})
        self.assertTrue(Router.from_config(cfg).providers[1].allows_private())
        self.assertFalse(load_config({'INSTINCT_PRODUCT':'atlas'}).trust_remote)

    def test_guard_before_availability(self):
        class Unsafe(Provider):
            def allows_private(self): return False
            def available(self): raise AssertionError('availability must not run')
            def chat(self,*a,**kw): raise AssertionError('chat must not run')
        self.assertFalse(Router([Unsafe()]).run(Task([],private=True)).ok)

    def test_malformed_responses_escalate_without_payload(self):
        bads=[None,[],{}, {'choices':[]}, {'choices':[{'message':None}]},
              reply(calls=[None]),reply(calls={}),reply(calls=[{}]),
              reply(calls=[{'function':{}}]), reply(calls=[{'function':{'name':3}}]),
              reply(calls=[{'function':{'name':'x'}}]),
              reply(calls=[{'function':{'name':'x','arguments':SECRET}}]),
              reply(calls=[{'function':{'name':'x','arguments':'[]'}}]),
              reply(calls=[{'function':{'name':'x','arguments':{}}}]),
              reply(calls=[{'function':{'name':'x','arguments':'null'}}]),reply(text=42)]
        for data in bads:
            with self.subTest(data=data):
                bad=InklingLocal('http://localhost:8000/v1','m',transport=lambda *a: data)
                good=InklingLocal('http://localhost:8000/v1','m',transport=lambda *a: reply())
                out=Router([bad,good]).run(Task([{'role':'user','content':SECRET}],private=True))
                self.assertTrue(out.ok)
                self.assertEqual(out.attempts[0].outcome,'error')
                self.assertNotIn(SECRET,str(out.attempts))
                with self.assertRaises(ProviderError): bad.chat([])
        def invalid(*a): raise json.JSONDecodeError(SECRET,SECRET,0)
        out=Router([InklingLocal('http://localhost:8000/v1','m',transport=invalid)]).run(Task([],private=True))
        self.assertEqual(out.attempts[0].outcome,'error')
        self.assertNotIn(SECRET,str(out.attempts))

    def test_valid_text_and_tools(self):
        calls=[{'function':{'name':'weather','arguments':'{"city":"Lagos"}'}}]
        p=InklingLocal('http://localhost:8000/v1','m',transport=lambda *a: reply('hi',calls))
        out=Router([p]).run(Task([],private=True)).result
        self.assertEqual(out.text,'hi')
        self.assertEqual(out.tool_calls,[{'name':'weather','arguments':{'city':'Lagos'}}])

    def test_http_redirect_and_decode_errors(self):
        hits=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.rfile.read(int(self.headers.get('Content-Length',0)))
                if self.path.startswith('/redirect'):
                    self.send_response(307); self.send_header('Location','/target'); self.end_headers()
                else:
                    self.send_response(500 if self.path.startswith('/http-error') else 200)
                    self.end_headers();self.wfile.write(SECRET.encode())
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302);self.send_header('Location','https://eviltheailibrary.co/');self.end_headers()
            def log_message(self,*a): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            for path in ('/redirect','/invalid','/http-error'):
                out=Router([InklingLocal(base+path,'m')]).run(Task([],private=True))
                self.assertFalse(out.ok);self.assertEqual(out.attempts[0].outcome,'error')
                self.assertNotIn(SECRET,str(out.attempts))
            self.assertIn('/redirect/chat/completions', hits)
            self.assertIn('/invalid/chat/completions', hits)
            self.assertIn('/http-error/chat/completions', hits)
            self.assertNotIn('/target',hits)
            # Test catalog redirect handler in a loopback fixture without real network.
            with patch('instinct_models.catalog._catalog_origin', return_value=True):
                with self.assertRaisesRegex(PermissionError, 'redirect refused'): _get(base)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_catalog_origin_boundary(self):
        valid=['https://theailibrary.co/tools/good','https://www.theailibrary.co:443/tools/good','/prompts/good']
        invalid=['https://eviltheailibrary.co/tools/evil','https://www.theailibrary.co.evil/tools/evil',
                 'http://www.theailibrary.co/tools/evil','https://www.theailibrary.co:444/tools/evil',
                 'https://user:pass@www.theailibrary.co/tools/evil','https://@www.theailibrary.co/tools/evil',
                 'javascript:bad','data:text/plain,bad','https://www.theailibrary.co:bad/tools/evil',
                 'https://[bad/tools/x','/submit/tool','/account/edit','/login','/signup']
        html=''.join(f'<a href="{u}">Entry {i}</a>' for i,u in enumerate(valid+invalid))
        cat=AILibraryCatalog(fetch=lambda u: 'User-agent: *\nAllow: /' if u.endswith('robots.txt') else html,min_interval_s=0)
        self.assertEqual([i.url for i in cat.browse()],valid[:2]+['https://www.theailibrary.co/prompts/good'])

    def test_catalog_cache_rate_limit_empty_and_invalid(self):
        now=[0.0]; seen=[]; sleeps=[]
        def fetch(u):
            seen.append(u)
            return 'User-agent: *\nAllow: /' if u.endswith('robots.txt') else '<a href="/tools/x">Tool X</a>'
        def sleep(t): sleeps.append(t);now[0]+=t
        c=AILibraryCatalog(fetch=fetch,clock=lambda:now[0],sleep=sleep,min_interval_s=2,ttl_s=10)
        self.assertEqual(len(c.browse()),1);c.browse();self.assertEqual(len(seen),2)
        c.browse('prompts');self.assertEqual(sleeps,[2.0])
        with self.assertRaises(ValueError):c.browse('unknown')
        self.assertEqual(c.browse(limit=0),[])
        for html in ('','<a href="/tools/broken"','<a>No href</a>'):
            c=AILibraryCatalog(fetch=lambda u:'User-agent: *\nAllow: /' if u.endswith('robots.txt') else html,min_interval_s=0)
            self.assertEqual(c.browse(),[])
