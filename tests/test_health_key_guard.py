import unittest
from unittest.mock import patch

from instinct_models import health


class HealthKeyGuardTests(unittest.TestCase):
    def test_key_never_sent_over_plain_http_to_remote_host(self):
        with patch("urllib.request.OpenerDirector.open") as op:
            r = health.probe("http://example.com/v1", "m", api_key="SECRET")
        op.assert_not_called()
        self.assertFalse(r["ok"])
        self.assertNotIn("SECRET", str(r))

    def test_key_allowed_for_https_and_loopback_http(self):
        self.assertTrue(health._key_safe("https://router.huggingface.co/v1"))
        self.assertTrue(health._key_safe("http://127.0.0.1:8080/v1"))
        self.assertFalse(health._key_safe("http://10.0.0.5:8080/v1"))
        self.assertFalse(health._key_safe("ftp://x"))
        self.assertFalse(health._key_safe("http://[bad"))

    def test_no_key_plain_http_probe_still_attempted(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=OSError("down")) as op:
            r = health.probe("http://example.com/v1", "m")
        op.assert_called_once()
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
