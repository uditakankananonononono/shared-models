import socket
import threading
import unittest

from instinct_models.health import probe


def serve(resp: bytes) -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]

    def run():
        c, _ = s.accept()
        c.recv(4096)
        c.sendall(resp)
        c.close()
        s.close()

    threading.Thread(target=run, daemon=True).start()
    return f"http://127.0.0.1:{port}"


class ProbeNeverRaises(unittest.TestCase):
    def test_hostile_servers_give_ok_false(self):
        for resp in (b"NOTHTTP\r\n\r\n", b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nabc",
                     b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n" + b"[" * 100000,
                     b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nZZ\r\n", b""):
            out = probe(serve(resp), "m")
            self.assertIs(out["ok"], False, resp[:30])

    def test_bad_base_urls_give_ok_false(self):
        for u in ("http://127.0.0.1:1/\x00x", "http://exa mple.com", None, 5, "", "http://[::1"):
            self.assertIs(probe(u, "m")["ok"], False, u)

    def test_good_server_still_ok(self):
        body = b'{"data":[{"id":"m"}]}'
        out = probe(serve(b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: %d\r\n\r\n" % len(body) + body), "m")
        self.assertTrue(out["ok"])
        self.assertTrue(out["model_listed"])


if __name__ == "__main__":
    unittest.main()
