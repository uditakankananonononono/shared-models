"""Signed-token regression assertions authored NOT RUN; product proposal unapplied."""
import unittest
from unittest.mock import patch
from instinct_models.lexical import LexicalToolModel


def tool(kind="number", required=False):
    return {"name": "set_amount", "parameters": {
        "properties": {"amount": {"type": kind}},
        "required": ["amount"] if required else []}}


class SignedNumericTests(unittest.TestCase):
    def setUp(self):
        self.model = LexicalToolModel()

    def test_negative_literals_never_become_positive_substrings(self):
        for literal, value in (("-12", -12), ("-12.5", -12.5), ("-0.5", -0.5), ("-012", -12), ("-00.5", -0.5)):
            with self.subTest(literal=literal):
                self.assertEqual(self.model.extract("set amount " + literal, tool()), {"amount": value})
        self.assertEqual(self.model.extract("set amount -12", tool("integer")), {"amount": -12})

    def test_explicit_plus_and_existing_positive_literals(self):
        for literal, value in (("+12", 12), ("+12.5", 12.5), ("12", 12), ("12.5", 12.5), ("12.50", 12.5)):
            with self.subTest(literal=literal):
                self.assertEqual(self.model.extract("set amount " + literal, tool()), {"amount": value})

    def test_integer_schema_rejects_signed_decimal(self):
        for literal in ("-12.5", "+12.5", "12.5"):
            self.assertEqual(self.model.extract("set amount " + literal, tool("integer")), {})

    def test_date_and_attached_or_unsupported_tokens_are_omitted(self):
        # Date hyphens are ambiguous delimiters, not negative-number evidence.
        for literal in ("2026-10-15", "a-12", "12kg", "--12", "+-12", "1e3", ".5", "12.", "1.2.3"):
            with self.subTest(literal=literal):
                self.assertEqual(self.model.extract("set amount " + literal, tool()), {})

    def test_unambiguous_signed_value_after_date_is_used(self):
        self.assertEqual(self.model.extract("on 2026-10-15 set amount -12", tool()), {"amount": -12})

    def test_numeric_token_can_have_parenthesis_delimiters(self):
        self.assertEqual(self.model.extract("set amount (-12.5)", tool()), {"amount": -12.5})

    def test_required_ambiguous_number_abstains_without_retraining(self):
        # Isolate extraction from classification. This does not claim model accuracy.
        with patch.object(self.model, "classify", return_value=("set_amount", 1.0)):
            self.assertIsNone(self.model.predict("set amount 2026-10-15", [tool(required=True)]))
            result = self.model.predict("set amount -12", [tool(required=True)])
        self.assertEqual(result["arguments"], {"amount": -12})
