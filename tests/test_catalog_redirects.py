"""Catalog requests must remain at the robots-checked URL."""
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from instinct_models.catalog import _get


class CatalogRedirectTests(unittest.TestCase):
    def test_redirect_never_contacts_unchecked_target(self):
        seen = []

        class Server(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/direct':
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'<a href="/tools/test">Test</a>')
                elif self.path == '/sink':
                    seen.append(self.path)
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_response(int(self.path.strip('/')))
                    self.send_header('Location', f'http://localhost:{self.server.server_port}/sink')
                    self.end_headers()
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            self.assertIn('Test', _get(base + '/direct', timeout=2))
            for code in (301, 302, 303, 307, 308):
                with self.subTest(code=code):
                    seen.clear()
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        _get(base + f'/{code}', timeout=2)
                    self.assertEqual(caught.exception.code, code)
                    self.assertEqual(seen, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class CatalogDomainTests(unittest.TestCase):
    def test_suffix_lookalikes_never_get_catalog_source_label(self):
        from instinct_models.catalog import AILibraryCatalog
        html = '''<a href="https://eviltheailibrary.co/tools/a">Evil suffix</a>
        <a href="https://theailibrary.co.attacker.invalid/tools/b">Evil extension</a>
        <a href="https://theailibrary.co/tools/c">Apex tool</a>
        <a href="https://www.theailibrary.co/tools/d">Main tool</a>
        <a href="https://sub.theailibrary.co/tools/e">Subdomain tool</a>'''
        catalog = AILibraryCatalog(fetch=lambda u: 'User-agent: *\nAllow: /\n'
                                   if u.endswith('/robots.txt') else html, min_interval_s=0)
        items = catalog.browse()
        self.assertEqual([i.title for i in items], ['Apex tool', 'Main tool', 'Subdomain tool'])
        self.assertTrue(all(i.source == 'theailibrary.co' for i in items))

    def test_only_web_scheme_links_receive_catalog_label(self):
        from instinct_models.catalog import AILibraryCatalog
        html = '''<a href="javascript://theailibrary.co/tools/a">Script link</a>
        <a href="ftp://theailibrary.co/tools/b">FTP link</a>
        <a href="file://theailibrary.co/tools/c">File link</a>
        <a href="http://theailibrary.co/tools/d">HTTP tool</a>
        <a href="https://www.theailibrary.co/tools/e">HTTPS tool</a>'''
        catalog = AILibraryCatalog(fetch=lambda u: 'User-agent: *\nAllow: /\n'
                                   if u.endswith('/robots.txt') else html, min_interval_s=0)
        self.assertEqual([i.title for i in catalog.browse()], ['HTTP tool', 'HTTPS tool'])
