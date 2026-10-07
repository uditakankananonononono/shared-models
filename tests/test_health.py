"""Shape validation and origin checks for zero-token health reads."""
import unittest
from unittest.mock import patch
from instinct_models.health import probe, hf_token_valid


class HealthTests(unittest.TestCase):
    def test_valid_json_wrong_shapes_are_unavailable_not_exceptions(self):
        for data in (None, [], 3, 'ok', {}, {'data': None}, {'data': {}},
                     {'data': ['model']}, {'data': [{}]}, {'data': [{'id': 3}]}):
            with self.subTest(data=data), patch('instinct_models.health._get', return_value=data):
                self.assertFalse(probe('http://localhost:1234/v1', 'm')['ok'])

    def test_model_inventory_is_not_inference(self):
        with patch('instinct_models.health._get', return_value={'data': [{'id': 'm'}]}):
            out = probe('http://localhost:1234/v1', 'm')
            self.assertTrue(out['ok'])
            self.assertTrue(out['model_listed'])
            self.assertFalse(probe('http://localhost:1234/v1', 'missing')['model_listed'])

    def test_only_exact_hf_router_origin_invokes_token_check(self):
        with patch('instinct_models.health._get', return_value={'data': []}), \
                patch('instinct_models.health.hf_token_valid', return_value=False) as check:
            for url in ('https://huggingface.co.attacker.invalid/v1',
                        'https://attacker.invalid/huggingface.co/v1',
                        'https://router.huggingface.co.attacker.invalid/v1'):
                self.assertTrue(probe(url, 'm')['ok'])
            check.assert_not_called()
            self.assertFalse(probe('https://router.huggingface.co/v1', 'm')['ok'])
            check.assert_called_once()

    def test_whoami_wrong_shape_does_not_authenticate(self):
        for data in (None, [], {'name': True}, {'name': ''}, {'name': 12}):
            with self.subTest(data=data), patch('instinct_models.health._get', return_value=data):
                self.assertIs(hf_token_valid('test-only-token'), False)
