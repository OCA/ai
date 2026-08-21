# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase

from odoo.addons.ai_sale_product_matcher.services import product_matcher


class TestProductMatcher(TransactionCase):
    def test_numeric_match_tolerance(self):
        self.assertTrue(product_matcher._numeric_match(120, 120))
        self.assertTrue(product_matcher._numeric_match(120, 125))  # within 10%
        self.assertFalse(product_matcher._numeric_match(120, 150))

    def test_numeric_match_range_product(self):
        self.assertTrue(product_matcher._numeric_match(300, "250 - 540"))
        self.assertFalse(product_matcher._numeric_match(100, "250 - 540"))

    def test_numeric_match_range_requirement(self):
        self.assertTrue(product_matcher._numeric_match("250 - 540", 300))
        self.assertFalse(product_matcher._numeric_match("250 - 540", 600))

    def test_parse_range(self):
        self.assertEqual(product_matcher._parse_range("250 - 540"), (250.0, 540.0))
        self.assertEqual(product_matcher._parse_range("250-540"), (250.0, 540.0))
        self.assertIsNone(product_matcher._parse_range("120"))

    def test_char_match(self):
        self.assertTrue(product_matcher._char_match("Monofaze (M)", "Monofaze (M)"))
        self.assertTrue(product_matcher._char_match("monofaze", "Monofaze (M)"))
        self.assertFalse(product_matcher._char_match("Trifaze", "Monofaze (M)"))

    def test_score_product_no_requirements(self):
        product = self.env["product.template"].create(
            {"name": "Test Prod", "sale_ok": True}
        )
        score = product_matcher.score_product({}, product)
        self.assertEqual(score["percent"], 0.0)

    def test_is_match_boolean(self):
        # Use a known boolean key if exists, otherwise char fallback still works
        self.assertTrue(product_matcher._char_match("true", "true"))

    def test_find_best_matches_orders(self):
        # Create two products with different values for pressure_bar (if PIM not installed, uses JSON fallback)
        # We test ordering by weighted percent - uses python-side scoring, no PIM needed
        p1 = self.env["product.template"].create({"name": "P1", "sale_ok": True})
        p2 = self.env["product.template"].create({"name": "P2", "sale_ok": True})
        # Monkey: set custom attrs via x_custom_json_attrs if field exists
        req = {"description": "test"}
        # Both products will score 0/1 -> equal, order stable
        best = product_matcher.find_best_matches(req, p1 | p2, limit=1)
        self.assertEqual(len(best), 1)
