"""SM-N6: confirmation-log intake diagnostics: UTF-16 guidance, size cap, non-finite numbers, duplicate ids."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from instinct_models.training.adapters import JsonlConfirmationLog
from instinct_models.training.dataset import build_needle_jsonl

TOOL = {"name": "add_task", "description": "add", "parameters": {"properties": {"title": {"type": "string"}, "n": {"type": "number"}}, "required": ["title"]}}


def rec(**kw):
    r = {"id": "r1", "query": "add task buy milk", "tools": [TOOL],
         "call": {"name": "add_task", "arguments": {"title": "buy milk"}}, "owner_decision": "confirmed"}
    r.update(kw)
    return r


def line(**kw):
    return json.dumps(rec(**kw)) + "\n"


class Intake(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)
        self.p = self.d / "log.jsonl"

    def tearDown(self):
        self._t.cleanup()

    def log(self, **kw):
        return JsonlConfirmationLog("atlas", self.p, **kw)

    # --- UTF-16
    def test_utf16_with_bom_gets_guidance(self):
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            with self.subTest(enc=enc):
                data = line().encode(enc)
                if enc != "utf-16":
                    data = (b"\xff\xfe" if enc.endswith("le") else b"\xfe\xff") + data
                self.p.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "UTF-16.*re-save"):
                    list(self.log().rows())

    def test_utf16_without_bom_gets_guidance(self):
        for enc in ("utf-16-le", "utf-16-be"):
            with self.subTest(enc=enc):
                self.p.write_bytes(line().encode(enc))
                with self.assertRaisesRegex(ValueError, "UTF-16"):
                    list(self.log().rows())

    def test_utf16_message_does_not_echo_content(self):
        self.p.write_bytes(line(query="SECRET-QUERY").encode("utf-16"))
        with self.assertRaises(ValueError) as cm:
            list(self.log().rows())
        self.assertNotIn("SECRET", str(cm.exception))

    def test_utf8_bom_and_bad_utf8_unchanged(self):
        self.p.write_bytes(b"\xef\xbb\xbf" + line().encode())
        self.assertEqual(len(list(self.log().rows())), 1)
        self.p.write_bytes(b'{"query":"\xff"}\n')
        with self.assertRaisesRegex(ValueError, "not valid UTF-8"):
            list(self.log().rows())

    def test_short_and_empty_files_are_not_utf16(self):
        self.p.write_bytes(b"")
        self.assertEqual(list(self.log().rows()), [])
        self.p.write_bytes(b"\n")
        self.assertEqual(list(self.log().rows()), [])

    # --- raw non-ASCII bytes (the JSON-escaped hostile-suite test is blind to the decode codec)
    def test_raw_non_ascii_utf8_bytes_decode_exactly_under_an_adverse_locale(self):
        raw = (json.dumps(rec(query="add task café 日本 \U0001f600", call={"name": "add_task", "arguments": {"title": "café"}}), ensure_ascii=False) + "\n").encode("utf-8")
        self.assertIn("café".encode("utf-8"), raw)  # really raw bytes, not \u escapes
        self.assertNotIn(b"\\u", raw)
        self.p.write_bytes(raw)
        with mock.patch("locale.getpreferredencoding", return_value="ascii"):
            rows = list(self.log().rows())
        self.assertEqual(rows[0].query, "add task café 日本 \U0001f600")
        self.assertEqual(rows[0].answers[0]["arguments"], {"title": "café"})

    # --- newlines
    def test_cr_only_and_crlf_logs_still_read(self):
        a, b = line(id="a").rstrip("\n"), line(id="b").rstrip("\n")
        for name, sep in (("cr", "\r"), ("crlf", "\r\n"), ("lf", "\n")):
            with self.subTest(sep=name):
                self.p.write_bytes((a + sep + b + sep).encode())
                lg = self.log()
                self.assertEqual([r.source_ref for r in lg.rows()], ["a", "b"])
                self.assertEqual(lg.skipped, [])

    def test_unicode_separators_inside_a_string_still_not_boundaries(self):
        self.p.write_text(json.dumps(rec(query="a\u2028b\x85c"), ensure_ascii=False) + "\n", encoding="utf-8")
        rows = list(self.log().rows())
        self.assertEqual([r.query for r in rows], ["a\u2028b\x85c"])

    # --- size cap
    def test_cap_boundary(self):
        data = line().encode()
        self.p.write_bytes(data)
        self.assertEqual(len(list(self.log(max_bytes=len(data)).rows())), 1)  # exactly at the cap
        with self.assertRaisesRegex(ValueError, "larger than"):
            list(self.log(max_bytes=len(data) - 1).rows())  # one byte over

    def test_default_cap_is_256_mib(self):
        self.assertEqual(self.log().max_bytes, 256 * 1024 * 1024)

    def test_cap_checked_on_fd_before_reading(self):
        self.p.write_bytes(line().encode())
        real = os.fstat

        class Big:
            def __init__(self, st):
                self._st = st
            st_size = 10**12
            def __getattr__(self, n):
                return getattr(self._st, n)
        with mock.patch("instinct_models.training.adapters.os.fstat", lambda fd: Big(real(fd))):
            with self.assertRaisesRegex(ValueError, "larger than"):
                list(self.log().rows())

    def test_growth_after_fstat_is_still_bounded(self):
        data = line().encode()
        self.p.write_bytes(data)
        real = os.fstat

        class Small:
            def __init__(self, st):
                self._st = st
            st_size = 1  # file looked small at check time, then "grew"
            def __getattr__(self, n):
                return getattr(self._st, n)
        with mock.patch("instinct_models.training.adapters.os.fstat", lambda fd: Small(real(fd))):
            with self.assertRaisesRegex(ValueError, "larger than"):
                list(self.log(max_bytes=len(data) - 1).rows())

    def test_read_is_bounded_to_cap_plus_one_and_growth_still_refused(self):
        data = line().encode()
        self.p.write_bytes(data)
        cap = len(data) - 1
        calls = []
        real_open = open

        class Spy:
            def __init__(self, f):
                self._f = f
            def __enter__(self):
                return self
            def __exit__(self, *a):
                self._f.close()
            def fileno(self):
                return self._f.fileno()
            def read(self, *a):
                calls.append(a)
                return self._f.read(*a)
        small = type("S", (), {"st_size": 1})()
        with mock.patch("instinct_models.training.adapters.open", lambda *a, **k: Spy(real_open(*a, **k)), create=True), \
                mock.patch("instinct_models.training.adapters.os.fstat", lambda fd: small):  # looked small, then "grew"
            with self.assertRaisesRegex(ValueError, "larger than"):
                list(self.log(max_bytes=cap).rows())
        self.assertEqual(calls, [(cap + 1,)])

    def test_bad_max_bytes_refused(self):
        for bad in (0, -1, True, 1.5, "9"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.log(max_bytes=bad)

    # --- non-finite
    def test_non_finite_numbers_skipped_with_line_and_reason(self):
        good = line(id="ok")
        bad = [
            '{"id":"n1","query":"q","tools":[],"call":{"name":"t","arguments":{"x":NaN}},"owner_decision":"confirmed"}\n',
            '{"id":"n2","query":"q","tools":[],"call":{"name":"t","arguments":{"x":Infinity}},"owner_decision":"confirmed"}\n',
            '{"id":"n3","query":"q","tools":[],"call":{"name":"t","arguments":{"x":-Infinity}},"owner_decision":"confirmed"}\n',
            '{"id":"n4","query":"q","tools":[],"call":{"name":"t","arguments":{"x":1e999}},"owner_decision":"confirmed"}\n',
            '{"id":"n5","query":NaN,"tools":[],"call":null,"owner_decision":"confirmed"}\n',
        ]
        self.p.write_text(good + "".join(bad) + good.replace("ok", "ok2"))
        lg = self.log()
        rows = list(lg.rows())
        self.assertEqual([r.source_ref for r in rows], ["ok", "ok2"])
        self.assertEqual([s["source_ref"] for s in lg.skipped], [f"log.jsonl:{n}" for n in range(2, 7)])
        self.assertTrue(all("non-finite" in s["reason"] for s in lg.skipped))

    def test_finite_numbers_unchanged(self):
        self.p.write_text(line(call={"name": "add_task", "arguments": {"title": "t", "n": 1.5e3}}) + line(id="r2", call={"name": "add_task", "arguments": {"title": "t", "n": -0.0}}))
        lg = self.log()
        self.assertEqual(len(list(lg.rows())), 2)
        self.assertEqual(lg.skipped, [])

    def test_end_to_end_build_with_mixed_log(self):
        self.p.write_text(line() + '{"id":"bad","query":"q","tools":[],"call":{"name":"t","arguments":{"x":NaN}},"owner_decision":"confirmed"}\n')
        lg = self.log()
        build_needle_jsonl(lg, self.d / "out" / "x.jsonl")
        self.assertEqual(len(lg.skipped), 1)
        self.assertIn("non-finite", lg.skipped[0]["reason"])

    # --- duplicate ids
    def test_duplicate_ids_kept_and_warned(self):
        self.p.write_text(line() + line(query="other query here") + line(id="r2") + line(id="r2"))
        lg = self.log()
        rows = list(lg.rows())
        self.assertEqual(len(rows), 4)  # nothing dropped
        self.assertEqual([w["source_ref"] for w in lg.warnings], ["log.jsonl:2", "log.jsonl:4"])
        self.assertIn("first seen at line 1", lg.warnings[0]["reason"])
        self.assertIn("first seen at line 3", lg.warnings[1]["reason"])
        self.assertEqual(lg.skipped, [])

    def test_missing_empty_and_odd_ids_are_not_counted(self):
        a = {k: v for k, v in rec().items() if k != "id"}
        self.p.write_text("".join(json.dumps(x) + "\n" for x in (a, a, rec(id=""), rec(id=""), rec(id=["x"]), rec(id=["x"]), rec(id=True), rec(id=True))))
        lg = self.log()
        self.assertEqual(len(list(lg.rows())), 8)
        self.assertEqual(lg.warnings, [])

    def test_warnings_reset_per_pass(self):
        self.p.write_text(line() + line())
        lg = self.log()
        list(lg.rows())
        list(lg.rows())
        self.assertEqual(len(lg.warnings), 1)

    def test_clean_log_has_no_warnings_or_skips(self):
        self.p.write_text(line(id="a") + line(id="b"))
        lg = self.log()
        self.assertEqual(len(list(lg.rows())), 2)
        self.assertEqual((lg.skipped, lg.warnings), ([], []))


if __name__ == "__main__":
    unittest.main()
