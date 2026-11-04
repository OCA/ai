# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Turn a customer order into a draft sales quotation, or update one.

The common rules are in ``OrderBuilder``. Here: the customer of the order, the
prices of its price list, its delivery address and the commitment date. The
products are never created: a product that cannot be identified stays pending
review.
"""

from datetime import datetime, time

from odoo import _
from odoo.tools import float_is_zero

from odoo.addons.ai_message_import.services.order_builder import OrderBuilder
from odoo.addons.ai_message_import.services.tools import normalize_text


class SaleOrderBuilder(OrderBuilder):
    order_model = "sale.order"
    line_model = "sale.order.line"
    order_link = "sale_order_id"
    line_link = "sale_line_id"
    qty_field = "product_uom_qty"
    tax_field = "tax_id"
    line_date_field = None
    order_fields = (
        "client_order_ref",
        "payment_term_id",
        "commitment_date",
        "partner_shipping_id",
    )
    line_fields = (
        "product_id",
        "product_uom_qty",
        "product_uom",
        "product_packaging_id",
        "price_unit",
        "discount",
    )
    product_ok_field = "sale_ok"
    packaging_usage = "sales"
    rank_field = "customer_rank"
    supplier_steps = False
    confirmed_states = ("sale",)

    def _role(self):
        return _("customer")

    def _order_label(self):
        return _("sales quotation")

    def _auto_create_partner(self):
        return self.config.auto_create_customer

    def _partner_min_confidence(self):
        return self.config.customer_min_confidence

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _header_values(self, partner):
        quote = self.quote
        # Only what the order states: a correction keeps the rest.
        values = {"client_order_ref": quote.quote_number} if quote.quote_number else {}
        term = self._payment_term(partner)
        if term is not None:
            values["payment_term_id"] = term.id
        if self.delivery_date:
            values["commitment_date"] = datetime.combine(
                self.delivery_date, time(12, 0)
            )
        shipping = self._shipping_partner(partner)
        if shipping:
            values["partner_shipping_id"] = shipping.id
        return values

    def _default_payment_term(self, partner):
        return partner.with_company(self.company).property_payment_term_id

    def _shipping_partner(self, partner):
        """The delivery address of the customer named by the order."""
        address = self.quote.delivery_address
        if not address:
            return None
        text = normalize_text(address)
        addresses = self.env["res.partner"].search(
            [("id", "child_of", partner.commercial_partner_id.id)]
        )
        found = addresses.filtered(
            lambda p: p.street and normalize_text(p.street) in text
        )
        if len(found) > 1:
            found = found.filtered(lambda p: p.type == "delivery") or found
        if len(found) == 1:
            self.note(
                _(
                    "Delivery address '%(address)s' matched to %(partner)s.",
                    address=address,
                    partner=found.display_name,
                )
            )
            return found
        self.incident(
            "delivery_address",
            _("Delivery address not found"),
            _(
                "The order asks for a delivery to '%(address)s', which matches "
                "%(count)s addresses of the customer. The usual delivery address "
                "of the customer is kept; no address was created.",
                address=address,
                count=len(found),
            ),
            values={"address": address},
        )
        self.note(
            _(
                "Delivery address '%(address)s' not found: the usual one is kept.",
                address=address,
            )
        )
        return None

    def _order_values(self, partner, header):
        quote = self.quote
        customer = partner.with_company(self.company)
        values = {
            "partner_id": partner.id,
            "company_id": self.company.id,
            "origin": quote.name,
            "ai_message_import_sender_id": quote.sender_id.id,
        }
        # The salesperson is computed by Odoo: the one of the customer, otherwise
        # the user that creates the quotation.
        pricelist = customer.property_product_pricelist
        if pricelist and pricelist.currency_id != self.company.currency_id:
            # The module only writes amounts in the currency of the company.
            values["pricelist_id"] = False
            self.incident(
                "currency",
                _("Price list in another currency"),
                _(
                    "The price list of the customer, %(pricelist)s, is in "
                    "%(currency)s. The quotation is in %(company_currency)s with "
                    "the sales prices of the products: set the price list by "
                    "hand if it must be used.",
                    pricelist=pricelist.display_name,
                    currency=pricelist.currency_id.name,
                    company_currency=self.company.currency_id.name,
                ),
                values={"pricelist": pricelist.display_name},
            )
        return values

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    def _target_packaging(self, line, plan):
        # Odoo suggests a packaging for the quantity: keep it.
        if plan.packaging:
            return plan.packaging.id
        if line.product_packaging_id.product_id == plan.product:
            return line.product_packaging_id.id
        return False

    def _recompute_line_prices(self, line):
        line.with_context(force_price_recomputation=True)._compute_price_unit()

    def _odoo_discount(self, line):
        """Discount of the price list, as Odoo computes it for the line."""
        pricelist = line.order_id.pricelist_id
        if not (
            pricelist
            and pricelist.discount_policy == "without_discount"
            and line.pricelist_item_id
        ):
            return 0.0
        line = line.with_company(line.company_id)
        pricelist_price = line._get_pricelist_price()
        base_price = line._get_pricelist_price_before_discount()
        if not base_price:
            return 0.0
        discount = (base_price - pricelist_price) / base_price * 100
        if (discount > 0 and base_price > 0) or (discount < 0 and base_price < 0):
            return discount
        return 0.0

    def _price_origin(self, line):
        if line.pricelist_item_id:
            return _(
                "price list %(pricelist)s",
                pricelist=line.order_id.pricelist_id.display_name,
            )
        return _("sales price of the product")

    def _check_zero_price(self, line, plan):
        if not float_is_zero(
            line.price_unit, precision_rounding=line.currency_id.rounding
        ):
            return
        self.incident(
            "price_zero",
            _("Zero price for %(line)s", line=plan.label),
            _(
                "%(product)s has no sales price for this customer: the price 0 is "
                "kept, check it before confirming. Quoted price: %(quoted)s.",
                product=line.product_id.display_name,
                quoted=self._amount(plan.quoted_price)
                if plan.quoted_price is not None
                else "-",
            ),
            qline=plan.qline,
        )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _freight_line_values(self, order, product, price):
        return {
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": 1.0,
            "product_uom": product.uom_id.id,
            "price_unit": price,
            "ai_message_import_line_kind": "freight",
            "sequence": 9999,
        }

    def _freight_tax_rate(self, product, order):
        taxes = order.fiscal_position_id.map_tax(
            product.taxes_id._filter_taxes_by_company(self.company)
        )
        if not taxes:
            return 0.0
        result = taxes.compute_all(100.0, currency=order.currency_id, product=product)
        excluded = result["total_excluded"]
        return (
            (result["total_included"] - excluded) / excluded * 100 if excluded else 0.0
        )
