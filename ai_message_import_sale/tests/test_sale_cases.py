# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import AiMessageSaleCase


@tagged("post_install", "-at_install")
class TestSaleCases(AiMessageSaleCase):
    """Less frequent cases of the customer orders."""

    def test_discount_of_the_price_list(self):
        # Odoo 17 defines the group in product, Odoo 18 in sale.
        group = self.env.ref(
            "sale.group_discount_per_so_line", raise_if_not_found=False
        ) or self.env.ref("product.group_discount_per_so_line")
        self.env.user.groups_id = [Command.link(group.id)]
        values = {
            "name": "Discounts",
            "currency_id": self.currency.id,
            "company_id": self.company.id,
            "item_ids": [
                Command.create(
                    {
                        "applied_on": "0_product_variant",
                        "product_id": self.product_cement.id,
                        "compute_price": "percentage",
                        "percent_price": 10,
                    }
                )
            ],
        }
        if "discount_policy" in self.env["product.pricelist"]._fields:
            # Odoo 17: the discount is shown only with this policy.
            values["discount_policy"] = "without_discount"
        pricelist = self.env["product.pricelist"].create(values)
        self.customer.with_company(self.company).property_product_pricelist = pricelist
        quote = self._run(
            self._order(
                [self._line("Cemento", 10, product_code="CEM-25", discount_percent=5)]
            )
        )
        line = quote.sale_order_id.order_line
        self.assertEqual(line.discount, 5.0)
        self.assertIn("replaces", quote.processing_notes)

    def test_transport_with_taxes_included(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                shipping={"amount": 36.3},
                prices_include_tax=True,
            )
        )
        freight = quote.sale_order_id.order_line.filtered(
            lambda ln: ln.ai_message_import_line_kind == "freight"
        )
        self.assertAlmostEqual(freight.price_unit, 30.0, places=2)

    def test_payment_terms_of_the_order(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                payment_terms={"text": "30 días", "days": 30},
            )
        )
        term = quote.sale_order_id.payment_term_id
        self.assertEqual(term.line_ids.nb_days, 30)

    def test_sales_of_a_sender_and_a_channel(self):
        quote = self._run(
            self._order(
                [
                    self._line("Azulejo", 10, product_code="AZ-2020"),
                    self._line("Muestra", 1, product_code="MUE-01"),
                ]
            )
        )
        order = quote.sale_order_id
        self.sender.invalidate_recordset()
        self.assertEqual(self.sender.sale_count, 1)
        for record in (self.sender, self.channel):
            action = record.action_view_sales()
            self.assertEqual(self.env["sale.order"].search(action["domain"]), order)
        incident = quote.incident_ids.filtered(lambda i: i.sale_order_id)[:1]
        self.assertEqual(incident.action_open_order()["res_id"], order.id)

    def test_confidences_are_checked(self):
        with self.assertRaises(ValidationError):
            self.config.customer_min_confidence = -1
